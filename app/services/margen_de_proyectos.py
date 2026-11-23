"""Ingreso, coste y margen de proyectos: el cálculo ÚNICO y en bloque (auditoría 22-11-2026, §7.2).

Había cuatro cálculos de margen que daban cifras distintas en pantallas distintas:

- el panel (``dashboard_service.get_profitability``): horas × ``billing_rate`` −
  ``cost_amount`` sin convertir, sin gastos, subcontrata ni ALM;
- rentabilidad (``profitability_service.calc_project_profitability``): el bueno,
  pero varias consultas por proyecto;
- la evolución del margen (``evolucion_del_margen``): las mismas reglas
  repartidas por fecha, con su propio código;
- el BI (``metrics.costs.margin_by_project`` y el KPI de margen medio del OLAP):
  otra vez horas × tarifa, o rentabilidad proyecto a proyecto (N+1).

Y el EVM (``evm_service.coste_real``) tenía su propio AC (sin ``is_active`` ni
moneda). Ahora todos salen de aquí. Reglas (las de rentabilidad):

- **Coste de personal**: cada imputación activa, ``cost_amount`` (o, sin él,
  horas × ``hourly_rate_snapshot``), convertida a la moneda de la empresa con
  el tipo de su fecha (por la moneda de la persona y, si es la de la empresa,
  por la del proyecto: ``coste_de_imputacion_en_moneda``).
- **Gastos y subcontrata**: ``costes_de_proyecto.partidas_externas``.
- **Licencias y equipos**: ``alm_costes.lineas`` del periodo, convertidas al
  último día del tramo.
- **Ingreso**: ``profitability_service.partidas_de_ingreso`` (tablas de tarifas
  → ``billing_rate`` → hitos facturados en ``billed_at``).
- **Margen** = ingreso − coste; ``margin_pct`` None sin ingreso.

Consultas: un número FIJO por llamada, sea uno o quinientos proyectos
(imputaciones, personas, hitos, tarifas ×3, gastos ×3, partes, proveedores, ALM,
una de tipos de cambio por moneda distinta: ``currency_rates_service.TablaDeTipos``)
— lo comprueba ``tests/test_margen_unico_2026_11_23.py``.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Callable, Hashable, Iterable, Optional

from sqlalchemy.orm import Session

#: Cifras acumuladas por proyecto y tramo. `total_cost` y el margen se derivan.
CAMPOS = ("revenue", "hours", "billable_hours", "internal_cost", "expenses_cost", "subcontract_cost", "alm_cost")
COSTES = ("internal_cost", "expenses_cost", "subcontract_cost", "alm_cost")


class _Imp:
    """Imputación ligera (sin ORM) con su persona, para el ingreso por tarifa."""

    __slots__ = ("project_id", "date", "hours", "is_billable", "user", "cost", "rate")

    def __init__(self, fila, usuario) -> None:
        (self.project_id, self.date, self.hours, self.is_billable, self.cost, self.rate) = (
            fila.project_id, fila.date, float(fila.hours or 0), bool(fila.is_billable),
            fila.cost_amount, fila.hourly_rate_snapshot)
        self.user = usuario


class _Persona:
    __slots__ = ("id", "currency", "job_title", "hourly_rate")

    def __init__(self, fila) -> None:
        self.id, self.currency, self.job_title, self.hourly_rate = fila.id, fila.currency, fila.job_title, fila.hourly_rate


def cerrar(d: dict) -> dict:
    """Totales derivados de unas cifras: coste total, margen y % (None sin ingreso)."""
    ingreso = round(float(d.get("revenue", 0.0)), 2)
    coste = round(sum(float(d.get(c, 0.0)) for c in COSTES), 2)
    margen = round(ingreso - coste, 2)
    salida = {c: round(float(d.get(c, 0.0)), 2) for c in CAMPOS}
    salida.update({"revenue": ingreso, "total_cost": coste, "margin": margen,
                   "margin_pct": round(margen / ingreso * 100, 1) if ingreso > 0 else None})
    return salida


def cifras_por_tramo(
    db: Session,
    proyectos: list,
    desde: Optional[date] = None,
    hasta: Optional[date] = None,
    *,
    clave: Optional[Callable[[date], Hashable]] = None,
    tramos: Optional[Iterable[tuple]] = None,
) -> tuple[dict, dict, dict]:
    """``({pid: {clave: {campo: importe}}}, {clave: {pid con imputación}}, {pid: moneda})``.

    ``clave(fecha)`` reparte cada partida en su tramo (sin ella, un único tramo
    ``"total"``); ``tramos`` = ``[(clave, primer día, último día)]`` para el
    coste de ALM, que se calcula por días. Todo en la moneda de la empresa de
    cada proyecto. Los tipos que falten quedan en el ``TiposQueFaltan`` activo.
    """
    from app.core import timeutil
    from app.models.financial import ProjectMilestone
    from app.models.imputation import Imputation
    from app.models.user import User
    from app.services import alm_costes
    from app.services.costes_de_proyecto import partidas_externas
    from app.services.currency_rates_service import TablaDeTipos
    from app.services.profitability_service import coste_de_imputacion_en_moneda, partidas_de_ingreso
    from app.services.rate_card_service import TarifasPrecargadas
    from app.services.settings_service.por_empresa import moneda_de_empresa

    datos: dict = defaultdict(lambda: defaultdict(lambda: dict.fromkeys(CAMPOS, 0.0)))
    activos: dict = defaultdict(set)
    if not proyectos:
        return datos, activos, {}
    clave = clave or (lambda _f: "total")
    if tramos is None:
        tramos = [("total", desde or alm_costes.ORIGEN, hasta or timeutil.today())]

    def dentro(f) -> bool:
        return f is not None and (desde is None or f >= desde) and (hasta is None or f <= hasta)

    por_id = {pr.id: pr for pr in proyectos}
    ids = list(por_id)
    monedas_org: dict = {}
    moneda: dict = {}
    for pr in proyectos:
        if pr.organization_id not in monedas_org:
            monedas_org[pr.organization_id] = moneda_de_empresa(db, registro=pr)
        moneda[pr.id] = monedas_org[pr.organization_id]

    with TablaDeTipos(db):
        q = db.query(Imputation.project_id, Imputation.user_id, Imputation.date, Imputation.hours,
                     Imputation.is_billable, Imputation.cost_amount, Imputation.hourly_rate_snapshot).filter(
            Imputation.project_id.in_(ids), Imputation.is_active.is_(True))
        if desde:
            q = q.filter(Imputation.date >= desde)
        if hasta:
            q = q.filter(Imputation.date <= hasta)
        filas = q.all()
        uids = {f.user_id for f in filas if f.user_id}
        personas = ({u.id: _Persona(u) for u in db.query(User.id, User.currency, User.job_title, User.hourly_rate)
                     .filter(User.id.in_(uids)).all()} if uids else {})

        hitos: dict = defaultdict(list)
        hq = db.query(ProjectMilestone).filter(
            ProjectMilestone.project_id.in_(ids), ProjectMilestone.is_active.is_(True),
            ProjectMilestone.is_billed.is_(True))
        if desde:
            hq = hq.filter(ProjectMilestone.billed_at >= desde)
        if hasta:
            hq = hq.filter(ProjectMilestone.billed_at <= hasta)
        for m in hq.all():
            hitos[m.project_id].append(m)

        fx: dict = {}
        imps_de: dict = defaultdict(list)
        for f in filas:
            pr = por_id[f.project_id]
            imp = _Imp(f, personas.get(f.user_id))
            k = clave(imp.date)
            d = datos[pr.id][k]
            d["hours"] += imp.hours
            if imp.is_billable:
                d["billable_hours"] += imp.hours
            coste = imp.cost if imp.cost is not None else (imp.hours * float(imp.rate) if imp.rate else 0.0)
            d["internal_cost"] += coste_de_imputacion_en_moneda(
                db, coste, getattr(imp.user, "currency", None), getattr(pr, "currency", None) or moneda[pr.id],
                moneda[pr.id], imp.date, fx)
            activos[k].add(pr.id)
            imps_de[pr.id].append(imp)

        tarifas = TarifasPrecargadas(db, proyectos)
        for pid, pr in por_id.items():
            for fecha, importe in partidas_de_ingreso(db, pr, imps_de.get(pid, []), hitos.get(pid, []),
                                                      tarifas.hay_tarifas(pr.organization_id), tarifas.tarifa):
                if dentro(fecha):
                    datos[pid][clave(fecha)]["revenue"] += float(importe or 0)

        por_moneda: dict = defaultdict(list)
        for pid in ids:
            por_moneda[moneda[pid]].append(pid)
        campo = {"gastos": "expenses_cost", "subcontrata": "subcontract_cost"}
        for mon, pids in por_moneda.items():
            for pid, fecha, tipo, importe in partidas_externas(db, pids, mon, desde, hasta):
                if dentro(fecha):
                    datos[pid][clave(fecha)][campo.get(tipo, "subcontract_cost")] += float(importe or 0)

        for k, ini, fin in tramos:
            for li in alm_costes.lineas(db, ini, fin, project_ids=ids):
                if li.project_id in por_id and li.amount:
                    datos[li.project_id][k]["alm_cost"] += alm_costes._convertir(
                        db, li.amount, li.currency, moneda[li.project_id], fin, fx)
    return datos, activos, moneda


def margen_en_bloque(db: Session, proyectos: list, desde: Optional[date] = None,
                     hasta: Optional[date] = None) -> dict:
    """``{project_id: cifras}`` del periodo, con ``CAMPOS`` + ``total_cost``,
    ``margin``, ``margin_pct``, ``currency`` y ``fx_warnings`` (los pares sin tipo
    de TODO el bloque: se contaron 1:1 y se avisa)."""
    from app.services.currency_rates_service import TiposQueFaltan
    with TiposQueFaltan() as faltan:
        datos, _, moneda = cifras_por_tramo(db, proyectos, desde, hasta)
    avisos = sorted(faltan)
    salida = {}
    for pr in proyectos:
        suma = dict.fromkeys(CAMPOS, 0.0)
        for d in datos.get(pr.id, {}).values():
            for c in CAMPOS:
                suma[c] += d[c]
        salida[pr.id] = {**cerrar(suma), "currency": moneda.get(pr.id), "fx_warnings": avisos}
    return salida
