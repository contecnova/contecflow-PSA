"""Evolución del margen por tramo y su desglose por proyecto o cliente (17-11-2026).

Lo que pinta la pantalla de Rentabilidad (``/profitability``) en «Evolución del
margen»: por cada tramo del periodo (día, semana o mes; ``app/core/periodo.py``)
ingreso, coste, margen, horas y proyectos activos; y los totales del periodo
por proyecto o por cliente.

Se calcula sobre la base transaccional, no sobre DuckDB: el esquema estrella
(``fact_imputations``) no tiene ingreso, y el ingreso depende de las tablas de
tarifas, de los hitos facturados y del cambio de moneda. Las reglas son las de
la cuenta de resultados de un proyecto (``profitability_service``), repartidas
por fecha, así que la suma de los tramos es la rentabilidad del periodo:

- **Coste** = personal (imputaciones activas, convertidas a la moneda de la
  empresa: ``coste_de_imputacion_en_moneda``) + gastos y subcontrata
  (``costes_de_proyecto.partidas_externas``, en su fecha) + licencias y equipos
  (``alm_costes.lineas`` de cada tramo).
- **Ingreso** = ``profitability_service.partidas_de_ingreso`` (tarifas →
  ``billing_rate`` → hitos facturados en ``billed_at``), decidido por proyecto
  con lo del periodo, como ``_ingreso_facturable``.
- **Margen** = ingreso − coste; ``margin_pct`` es ``None`` sin ingreso (un
  margen sin ingreso no es 0 %, es que no hay dato).
- **Proyectos activos** = proyectos con alguna imputación en el tramo (lo que
  contaba la consulta OLAP).

Multiempresa: la sesión de la petición filtra por empresa y, además, solo se
leen proyectos con ``organization_id`` de quien pregunta. Un proyecto o cliente
de otra empresa da 404 con código.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.core.periodo import FORMATO_CLAVE, Periodo
from app.core.codigos_de_error import ErrorConCodigo

POR = ("proyecto", "cliente")
_CAMPOS = ("revenue", "total_cost", "hours")


def _proyectos(db: Session, org_id, proyecto_id: Optional[str], cliente_id: Optional[str]) -> list:
    from app.models.clients import Client
    from app.models.project import Project
    q = db.query(Project).filter(Project.is_active.is_(True))
    if org_id is not None:
        q = q.filter(Project.organization_id == str(org_id))
    if proyecto_id:
        q = q.filter(Project.id == proyecto_id)
        if q.first() is None:
            raise error(404, "proyecto_no_encontrado")
    if cliente_id:
        cq = db.query(Client.id).filter(Client.id == cliente_id)
        if org_id is not None:
            cq = cq.filter(Client.organization_id == str(org_id))
        if cq.first() is None:
            raise error(404, "cliente_no_encontrado")
        q = q.filter(Project.client_id == cliente_id)
    return q.all()


def _tramos(p: Periodo) -> list[tuple[str, object, object]]:
    """(clave, primer día, último día) de cada tramo, recortados al periodo."""
    claves = p.claves()
    salida = []
    for i, k in enumerate(claves):
        inicio = datetime.strptime(k, FORMATO_CLAVE).date()
        fin = (datetime.strptime(claves[i + 1], FORMATO_CLAVE).date() - timedelta(days=1)
               if i + 1 < len(claves) else p.fecha_hasta)
        salida.append((k, max(inicio, p.fecha_desde), min(fin, p.fecha_hasta)))
    return salida


def _por_proyecto_y_tramo(db: Session, p: Periodo, proyectos: list) -> tuple[dict, dict]:
    """``({project_id: {clave: {revenue, total_cost, hours}}}, {clave: {project_id con imputación}})``."""
    from app.models.financial import ProjectMilestone
    from app.models.imputation import Imputation
    from app.models.user import User
    from app.services import alm_costes
    from app.services.costes_de_proyecto import partidas_externas
    from app.services.profitability_service import (
        _hay_tarifas, coste_de_imputacion_en_moneda, partidas_de_ingreso,
    )

    # 18-11-2026: moneda de la empresa (sesión o, para el superadmin, la de los proyectos).
    from app.services.settings_service.por_empresa import moneda_de_empresa
    moneda = moneda_de_empresa(db, registro=proyectos[0] if proyectos else None)
    datos: dict = defaultdict(lambda: defaultdict(lambda: dict.fromkeys(_CAMPOS, 0.0)))
    activos: dict = defaultdict(set)
    if not proyectos:
        return datos, activos
    por_id = {pr.id: pr for pr in proyectos}
    ids = list(por_id)
    desde, hasta = p.fecha_desde, p.fecha_hasta

    imps = db.query(Imputation).filter(Imputation.project_id.in_(ids), Imputation.is_active.is_(True),
                                       Imputation.date >= desde, Imputation.date <= hasta).all()
    usuarios = {u.id: u for u in db.query(User).filter(User.id.in_({i.user_id for i in imps if i.user_id})).all()} \
        if imps else {}
    hitos: dict = defaultdict(list)
    for m in db.query(ProjectMilestone).filter(
            ProjectMilestone.project_id.in_(ids), ProjectMilestone.is_active.is_(True),
            ProjectMilestone.is_billed.is_(True), ProjectMilestone.billed_at >= desde,
            ProjectMilestone.billed_at <= hasta).all():
        hitos[m.project_id].append(m)

    fx: dict = {}
    imps_de: dict = defaultdict(list)
    for i in imps:
        pr = por_id[i.project_id]
        k = p.clave(i.date)
        u = usuarios.get(i.user_id)
        d = datos[i.project_id][k]
        d["hours"] += float(i.hours or 0)
        d["total_cost"] += coste_de_imputacion_en_moneda(
            db, i.cost_amount, getattr(u, "currency", None), getattr(pr, "currency", None) or moneda, moneda,
            i.date, fx)
        activos[k].add(i.project_id)
        imps_de[i.project_id].append(i)

    # Ingreso: la regla del proyecto con lo del periodo; la persona para la tarifa.
    hay_tarifas: dict = {}
    for pid, pr in por_id.items():
        lista = imps_de.get(pid, [])
        org = pr.organization_id
        if org not in hay_tarifas:
            hay_tarifas[org] = _hay_tarifas(db, pr)
        for fecha, importe in partidas_de_ingreso(db, pr, [_ConPersona(i, usuarios.get(i.user_id)) for i in lista],
                                                  hitos.get(pid, []), hay_tarifas[org]):
            if fecha is not None and p.contiene(fecha):
                datos[pid][p.clave(fecha)]["revenue"] += float(importe or 0)

    for pid, fecha, _tipo, importe in partidas_externas(db, ids, moneda, desde, hasta):
        if fecha is not None and p.contiene(fecha):
            datos[pid][p.clave(fecha)]["total_cost"] += float(importe or 0)

    # Licencias y equipos: el coste diario de ALM de cada tramo, por proyecto.
    for k, ini, fin in _tramos(p):
        for li in alm_costes.lineas(db, ini, fin):
            if li.project_id in por_id and li.amount:
                datos[li.project_id][k]["total_cost"] += alm_costes._convertir(db, li.amount, li.currency, moneda, fin, fx)
    return datos, activos


class _ConPersona:
    """Imputación con su persona (``user``) ya cargada, sin tocar la relación del ORM."""

    __slots__ = ("date", "hours", "is_billable", "user")

    def __init__(self, imp, usuario) -> None:
        self.date, self.hours, self.is_billable, self.user = imp.date, imp.hours, imp.is_billable, usuario


def _cerrar(d: dict) -> dict:
    ingreso, coste = round(d.get("revenue", 0.0), 2), round(d.get("total_cost", 0.0), 2)
    margen = round(ingreso - coste, 2)
    return {"revenue": ingreso, "total_cost": coste, "margin": margen,
            "margin_pct": round(margen / ingreso * 100, 1) if ingreso > 0 else None,
            "hours": round(d.get("hours", 0.0), 2)}


def serie(db: Session, org_id, p: Periodo, *, proyecto_id: Optional[str] = None,
          cliente_id: Optional[str] = None) -> list[dict]:
    """Un punto por tramo: ``t``, ``clave``, ``month``, ``granularidad``, ``revenue``,
    ``total_cost``, ``margin``, ``margin_pct``, ``hours`` y ``active_projects``."""
    datos, activos = _por_proyecto_y_tramo(db, p, _proyectos(db, org_id, proyecto_id, cliente_id))
    suma: dict = defaultdict(lambda: dict.fromkeys(_CAMPOS, 0.0))
    for tramos in datos.values():
        for k, d in tramos.items():
            for c in _CAMPOS:
                suma[k][c] += d[c]
    vacio = {**_cerrar({}), "active_projects": 0}
    filas = {k: {**_cerrar(d), "active_projects": len(activos.get(k, ()))} for k, d in suma.items()}
    puntos = p.rellenar(filas, vacio=vacio)
    for punto in puntos:
        punto["month"] = punto["clave"][:7]
        punto["granularidad"] = p.granularidad
    return puntos


def desglose(db: Session, org_id, p: Periodo, por: str = "proyecto", *, limite: int = 50,
             proyecto_id: Optional[str] = None, cliente_id: Optional[str] = None) -> list[dict]:
    """Totales del periodo por proyecto o por cliente, de más a menos margen.

    Cada fila: ``id``, ``codigo``, ``nombre``, ``revenue``, ``total_cost``,
    ``margin``, ``margin_pct``, ``hours`` (y ``proyectos`` por cliente). Los
    proyectos sin cliente se agrupan en una fila ``id = None``."""
    from app.models.clients import Client
    if por not in POR:
        raise ErrorConCodigo("valor_no_valido", detail=f"desglose no admitido: {por!r}", valor=por)
    proyectos = _proyectos(db, org_id, proyecto_id, cliente_id)
    datos, _ = _por_proyecto_y_tramo(db, p, proyectos)
    totales: dict = {}
    for pr in proyectos:
        t = dict.fromkeys(_CAMPOS, 0.0)
        for d in datos.get(pr.id, {}).values():
            for c in _CAMPOS:
                t[c] += d[c]
        if not any(t.values()):
            continue
        if por == "proyecto":
            totales[pr.id] = {"id": pr.id, "codigo": pr.code, "nombre": pr.name, **t}
            continue
        fila = totales.setdefault(pr.client_id, {"id": pr.client_id, "codigo": None,
                                                 "nombre": None, "proyectos": 0, **dict.fromkeys(_CAMPOS, 0.0)})
        fila["proyectos"] += 1
        for c in _CAMPOS:
            fila[c] += t[c]
    if por == "cliente":
        ids = [k for k in totales if k]
        nombres = {c.id: (c.name, c.short_name) for c in db.query(Client).filter(Client.id.in_(ids)).all()} if ids else {}
        for k, fila in totales.items():
            nombre, corto = nombres.get(k, (None, None))
            fila["nombre"], fila["codigo"] = nombre, corto
    filas = [{**{k: v for k, v in f.items() if k not in _CAMPOS}, **_cerrar(f)} for f in totales.values()]
    filas.sort(key=lambda f: f["margin"], reverse=True)
    return filas[:max(1, limite)]
