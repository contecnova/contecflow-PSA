"""Coste de una unidad interna en un periodo, por fuente (docs/CLIENTES_INTERNOS.md §4).

Fuentes: `horas`, `precio_cerrado`, `catalogo`, `licencias`, `activos`,
`software`, `reparto`. Cada línea: `{source, description, project_id,
project_name, quantity, unit_amount, amount, source_ref}` en la moneda de la
empresa. Nada se guarda aquí: el cargo (`cargos.py`) congela las líneas.
"""
from __future__ import annotations

import calendar
import json
from datetime import date, datetime, time, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.models.clientes_internos import CRITERIOS_REPARTO, InternalSharedCost
from app.services.clientes_internos import unidades as U

FUENTES = ("horas", "precio_cerrado", "catalogo", "licencias", "activos", "software", "reparto")


def _r(x) -> float:
    return round(float(x or 0), 2)


def periodo(texto: str) -> tuple[date, date]:
    """'AAAA-MM' -> (primer día, último día)."""
    try:
        y, m = (int(p) for p in str(texto).split("-")[:2])
        return date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])
    except Exception:
        raise error(422, "interno_periodo_no_valido")


def _linea(source, description, amount, *, project=None, quantity=None, unit_amount=None, ref=None) -> dict:
    return {"source": source, "description": description[:500], "project_id": getattr(project, "id", None),
            "project_name": getattr(project, "name", None), "quantity": None if quantity is None else round(quantity, 2),
            "unit_amount": None if unit_amount is None else round(unit_amount, 4), "amount": _r(amount),
            "source_ref": ref}


def proyectos_de(db: Session, unidad) -> list:
    from app.models.project import Project
    return db.query(Project).filter(Project.client_id == unidad.id, Project.is_active.is_(True)).all()


def _es_precio_cerrado(p) -> bool:
    return (p.billing_type or "") == "fixed_price" and (p.contract_amount or 0) > 0


# ── Horas ────────────────────────────────────────────────────────────────────

def _tarifas(db: Session, unidad) -> tuple[dict, Optional[float]]:
    """(etiqueta en minúsculas -> billing_rate, tarifa por defecto) de la tabla interna."""
    if unidad.cost_method != "tarifa_interna" or not unidad.internal_rate_table_id:
        return {}, None
    from app.models.advanced_config import RateEntry
    filas = db.query(RateEntry).filter(RateEntry.table_id == unidad.internal_rate_table_id).all()
    por_etiqueta = {(e.label or "").strip().lower(): float(e.billing_rate) for e in filas if e.billing_rate}
    defecto = next((float(e.billing_rate) for e in filas if e.billing_rate), None)
    return por_etiqueta, defecto


def _horas(db: Session, unidad, proyectos: list, desde: date, hasta: date) -> list[dict]:
    from app.models.imputation import Imputation
    from app.models.user import User
    from app.services import cost_service
    ids = [p.id for p in proyectos if not _es_precio_cerrado(p)]
    if not ids:
        return []
    por_id = {p.id: p for p in proyectos}
    tarifas, defecto = _tarifas(db, unidad)
    agregado: dict = {}
    usuarios: dict = {}
    for imp in db.query(Imputation).filter(Imputation.project_id.in_(ids), Imputation.is_active.is_(True),
                                           Imputation.date >= desde, Imputation.date <= hasta):
        horas = float(imp.hours or 0)
        if horas <= 0:
            continue
        if imp.user_id not in usuarios:
            usuarios[imp.user_id] = db.get(User, imp.user_id)
        u = usuarios[imp.user_id]
        if tarifas or defecto:
            tarifa = tarifas.get(((u.job_title if u else "") or "").strip().lower(), defecto) or 0.0
            importe = horas * tarifa
        elif imp.cost_amount is not None:
            importe = float(imp.cost_amount)
        else:
            importe = horas * float(cost_service.cost_per_hour(db, u, imp.date, imp.project_id) or 0) if u else 0.0
        a = agregado.setdefault(imp.project_id, [0.0, 0.0])
        a[0] += horas
        a[1] += importe
    salida = []
    for pid, (horas, importe) in agregado.items():
        p = por_id[pid]
        salida.append(_linea("horas", f"{p.code} {p.name}", importe, project=p, quantity=horas,
                             unit_amount=importe / horas if horas else None, ref=pid))
    return salida


# ── Precio cerrado ───────────────────────────────────────────────────────────

def _meses_entre(a: date, b: date) -> int:
    return max(1, (b.year - a.year) * 12 + b.month - a.month + 1)


def _precio_cerrado(db: Session, proyectos: list, desde: date, hasta: date) -> list[dict]:
    from app.models.financial import ProjectMilestone
    salida = []
    ini = datetime.combine(desde, time.min, tzinfo=timezone.utc)
    fin = datetime.combine(hasta, time.max, tzinfo=timezone.utc)
    for p in proyectos:
        if not _es_precio_cerrado(p):
            continue
        hitos = db.query(ProjectMilestone).filter(ProjectMilestone.project_id == p.id,
                                                  ProjectMilestone.is_active.is_(True)).all()
        if hitos:
            del_periodo = [h for h in hitos if h.approved_at is not None and ini <= _utc(h.approved_at) <= fin]
            if del_periodo:
                parte = float(p.contract_amount) * len(del_periodo) / len(hitos)
                salida.append(_linea("precio_cerrado", f"{p.code} {p.name}", parte, project=p,
                                     quantity=len(del_periodo), unit_amount=float(p.contract_amount) / len(hitos),
                                     ref=p.id))
            continue
        inicio = p.start_date or desde
        final = p.end_date_planned or p.end_date_real or inicio
        if final < desde or inicio > hasta:
            continue
        meses_total = _meses_entre(inicio, final)
        meses = _meses_entre(max(inicio, desde), min(final, hasta))
        salida.append(_linea("precio_cerrado", f"{p.code} {p.name}", float(p.contract_amount) * meses / meses_total,
                             project=p, quantity=meses, unit_amount=float(p.contract_amount) / meses_total, ref=p.id))
    return salida


def _utc(dt):
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ── Catálogo interno ─────────────────────────────────────────────────────────

def _tickets_del_periodo(db: Session, unidad, desde: date, hasta: date, resueltos: bool = False):
    from app.models.service_desk.tickets import Ticket
    ini = datetime.combine(desde, time.min, tzinfo=timezone.utc)
    fin = datetime.combine(hasta, time.max, tzinfo=timezone.utc)
    q = db.query(Ticket).filter(Ticket.client_id == unidad.id)
    if resueltos:
        return q.filter(Ticket.resolved_at.isnot(None), Ticket.resolved_at >= ini, Ticket.resolved_at <= fin)
    return q.filter(Ticket.created_at >= ini, Ticket.created_at <= fin)


def _catalogo(db: Session, unidad, desde: date, hasta: date) -> list[dict]:
    from app.models.service_desk.catalog import ServiceItem
    agregado: dict = {}
    for t in _tickets_del_periodo(db, unidad, desde, hasta, resueltos=True).filter(
            _tick_con_servicio()):
        agregado[t.service_item_id] = agregado.get(t.service_item_id, 0) + 1
    salida = []
    for sid, n in agregado.items():
        s = db.get(ServiceItem, sid)
        if s is None or not s.internal_price:
            continue
        salida.append(_linea("catalogo", s.name, n * float(s.internal_price), quantity=n,
                             unit_amount=float(s.internal_price), ref=sid))
    return salida


def _tick_con_servicio():
    from app.models.service_desk.tickets import Ticket
    return Ticket.service_item_id.isnot(None)


# ── Licencias y equipos (ALM) ────────────────────────────────────────────────

def _alm(db: Session, unidad, desde: date, hasta: date, miembros: set) -> tuple[list[dict], set]:
    """Líneas de ALM de la unidad y los ids de licencia ya contados."""
    from app.services import alm_costes
    from app.services.settings_service import por_empresa
    moneda = por_empresa.moneda_de_empresa(db, unidad.organization_id)
    fx: dict = {}
    agregado: dict = {}
    licencias = set()
    try:
        filas = alm_costes.lineas(db, desde, hasta)
    except Exception:
        return [], licencias
    for li in filas:
        de_la_unidad = (li.client_id == unidad.id
                        or (unidad.cost_center_id and li.cost_center_id == unidad.cost_center_id)
                        or (li.holder_type == "user" and li.holder_id in miembros))
        if not de_la_unidad:
            continue
        fuente = "activos" if li.resource_type == "asset" else "licencias"
        importe = alm_costes._convertir(db, li.amount, li.currency, moneda, hasta, fx)
        a = agregado.setdefault((fuente, li.resource_id), [li.resource_name, 0.0, 0])
        a[1] += importe
        a[2] = max(a[2], li.days)
        if li.license_id:
            licencias.add(li.license_id)
    salida = [_linea(f, nombre, imp, quantity=dias, ref=rid) for (f, rid), (nombre, imp, dias) in agregado.items()]
    return salida, licencias


# ── Aplicaciones propias (CMDB de software) ──────────────────────────────────

def aplicaciones_de(db: Session, unidad, miembros: set) -> list:
    from app.models.cmdb_software import SoftwareInstance, SoftwareProduct
    ids = {i.product_id for i in db.query(SoftwareInstance).filter(SoftwareInstance.client_id == unidad.id,
                                                                   SoftwareInstance.is_active.is_(True))}
    q = db.query(SoftwareProduct).filter(SoftwareProduct.is_active.is_(True))
    propios = q.filter(SoftwareProduct.owner_user_id.in_(miembros)).all() if miembros else []
    otros = q.filter(SoftwareProduct.id.in_(ids - {p.id for p in propios})).all() if ids else []
    return propios + otros


def tco_de_aplicacion(db: Session, producto, desde: date, hasta: date, moneda: str,
                      excluir_licencias: Optional[set] = None) -> dict:
    """Licencias enlazadas (ALM) + horas del proyecto del producto en el periodo."""
    from app.models.cmdb_software import SoftwareInstance, SoftwareProductLicense
    from app.models.imputation import Imputation
    from app.services import alm_costes
    lic_ids = {r.license_id for r in db.query(SoftwareProductLicense).filter(
        SoftwareProductLicense.product_id == producto.id)} - (excluir_licencias or set())
    licencias = 0.0
    if lic_ids:
        fx: dict = {}
        try:
            for li in alm_costes.lineas(db, desde, hasta):
                if li.license_id in lic_ids:
                    licencias += alm_costes._convertir(db, li.amount, li.currency, moneda, hasta, fx)
        except Exception:
            licencias = 0.0
    horas = 0.0
    if producto.project_id:
        for imp in db.query(Imputation).filter(Imputation.project_id == producto.project_id,
                                               Imputation.is_active.is_(True), Imputation.date >= desde,
                                               Imputation.date <= hasta):
            horas += float(imp.cost_amount or 0)
    instancias = db.query(SoftwareInstance).filter(SoftwareInstance.product_id == producto.id,
                                                   SoftwareInstance.is_active.is_(True)).count()
    return {"product_id": producto.id, "name": producto.name, "instances": instancias,
            "licenses": _r(licencias), "hours": _r(horas), "total": _r(licencias + horas)}


def _software(db: Session, unidad, desde: date, hasta: date, miembros: set, ya_contadas: set,
              proyectos_unidad: set) -> list[dict]:
    from app.services.settings_service import por_empresa
    moneda = por_empresa.moneda_de_empresa(db, unidad.organization_id)
    salida = []
    for p in aplicaciones_de(db, unidad, miembros):
        t = tco_de_aplicacion(db, p, desde, hasta, moneda, excluir_licencias=ya_contadas)
        # Las horas de un proyecto de la propia unidad ya están en «horas».
        importe = t["licenses"] + (0 if p.project_id in proyectos_unidad else t["hours"])
        if importe:
            salida.append(_linea("software", p.name, importe, ref=p.id))
    return salida


# ── Reparto de servicios compartidos ─────────────────────────────────────────

def conductor(db: Session, criterio: str, unidad, desde: date, hasta: date) -> float:
    """Valor del criterio de reparto para la unidad en el periodo."""
    if criterio == "usuarios":
        return float(len(U.miembros_ids(db, unidad)))
    if criterio == "tickets":
        return float(_tickets_del_periodo(db, unidad, desde, hasta).count())
    if criterio == "licencias":
        from app.models.alm import ALMAsignacion
        ids = U.miembros_ids(db, unidad)
        q = db.query(ALMAsignacion).filter(ALMAsignacion.status == "active", ALMAsignacion.license_id.isnot(None))
        return float(q.filter((ALMAsignacion.holder_client_id == unidad.id)
                              | (ALMAsignacion.holder_user_id.in_(ids or {""}))).count())
    if criterio == "software":
        from app.models.cmdb_software import SoftwareInstance
        return float(db.query(SoftwareInstance).filter(SoftwareInstance.client_id == unidad.id,
                                                       SoftwareInstance.is_active.is_(True)).count())
    return 0.0


def _cuotas_fijas(servicio) -> dict:
    try:
        d = json.loads(servicio.fixed_shares or "{}")
        return {str(k): float(v) for k, v in d.items()} if isinstance(d, dict) else {}
    except Exception:
        return {}


def reparto(db: Session, servicio, desde: date, hasta: date, usuario=None) -> dict:
    """Reparto del coste del servicio en el periodo entre todas las unidades activas."""
    meses = _meses_entre(desde, hasta)
    total = float(servicio.monthly_amount or 0) * meses
    unidades = U.unidades(db, usuario)
    if servicio.criterion == "fijo":
        cuotas = _cuotas_fijas(servicio)
        filas = [(u, cuotas.get(u.id, 0.0)) for u in unidades]
        suma = sum(v for _, v in filas) or 0.0
        pcts = [(u, v, (v / 100.0) if suma else 0.0) for u, v in filas]
    else:
        filas = [(u, conductor(db, servicio.criterion, u, desde, hasta)) for u in unidades]
        suma = sum(v for _, v in filas)
        pcts = [(u, v, (v / suma) if suma else 0.0) for u, v in filas]
    return {"id": servicio.id, "name": servicio.name, "criterion": servicio.criterion,
            "period_from": str(desde), "period_to": str(hasta), "total": _r(total), "currency": servicio.currency,
            "shares": [{"client_id": u.id, "client_name": u.name, "driver": round(v, 2), "pct": round(p * 100, 2),
                        "amount": _r(total * p)} for u, v, p in pcts if p]}


def _reparto(db: Session, unidad, desde: date, hasta: date) -> list[dict]:
    salida = []
    for s in db.query(InternalSharedCost).filter(InternalSharedCost.is_active.is_(True)):
        if s.organization_id and unidad.organization_id and s.organization_id != unidad.organization_id:
            continue
        r = reparto(db, s, desde, hasta)
        mia = next((x for x in r["shares"] if x["client_id"] == unidad.id), None)
        if mia and mia["amount"]:
            salida.append(_linea("reparto", f"{s.name} ({mia['pct']} %)", mia["amount"], quantity=mia["driver"],
                                 ref=s.id))
    return salida


# ── Coste total ──────────────────────────────────────────────────────────────

def coste(db: Session, unidad, desde: date, hasta: date) -> dict:
    """Líneas y totales por fuente de la unidad en [desde, hasta]."""
    from app.services.settings_service import por_empresa
    proyectos = proyectos_de(db, unidad)
    miembros = U.miembros_ids(db, unidad)
    alm, contadas = _alm(db, unidad, desde, hasta, miembros)
    lineas = (_horas(db, unidad, proyectos, desde, hasta)
              + _precio_cerrado(db, proyectos, desde, hasta)
              + _catalogo(db, unidad, desde, hasta)
              + alm
              + _software(db, unidad, desde, hasta, miembros, contadas, {p.id for p in proyectos})
              + _reparto(db, unidad, desde, hasta))
    por_fuente = {f: 0.0 for f in FUENTES}
    for li in lineas:
        por_fuente[li["source"]] = _r(por_fuente[li["source"]] + li["amount"])
    return {"from": str(desde), "to": str(hasta), "currency": por_empresa.moneda_de_empresa(db, unidad.organization_id),
            "total": _r(sum(por_fuente.values())), "by_source": por_fuente, "lines": lineas}


def tco(db: Session, unidad, year: int) -> dict:
    from app.core import timeutil
    from app.services.settings_service import por_empresa
    desde = date(year, 1, 1)
    hasta = min(date(year, 12, 31), timeutil.today())
    moneda = por_empresa.moneda_de_empresa(db, unidad.organization_id)
    miembros = U.miembros_ids(db, unidad)
    items = [tco_de_aplicacion(db, p, desde, hasta, moneda) for p in aplicaciones_de(db, unidad, miembros)]
    return {"year": year, "currency": moneda, "items": sorted(items, key=lambda x: -x["total"])}


# ── Servicios compartidos (CRUD) ─────────────────────────────────────────────

def servicio_dict(s) -> dict:
    return {"id": s.id, "name": s.name, "description": s.description, "monthly_amount": _r(s.monthly_amount),
            "currency": s.currency, "criterion": s.criterion, "fixed_shares": _cuotas_fijas(s),
            "is_active": bool(s.is_active)}


def listar_servicios(db: Session) -> list[dict]:
    return [servicio_dict(s) for s in db.query(InternalSharedCost).order_by(InternalSharedCost.name)]


def _servicio_o_404(db: Session, sid: str):
    s = db.get(InternalSharedCost, sid)
    if s is None:
        raise error(404, "no_encontrado", detail="Servicio compartido no encontrado", que="servicio_compartido")
    return s


def guardar_servicio(db: Session, actor, datos: dict, sid: Optional[str] = None) -> dict:
    from app.services.audit import audit_log
    from app.services.settings_service import por_empresa
    s = _servicio_o_404(db, sid) if sid else InternalSharedCost(
        organization_id=actor.organization_id, created_by=actor.id,
        currency=por_empresa.moneda_de_empresa(db, actor.organization_id))
    antes = servicio_dict(s) if sid else None
    criterio = datos.get("criterion", s.criterion or "usuarios")
    if criterio not in CRITERIOS_REPARTO:
        raise error(422, "interno_criterio_no_valido", valor=criterio)
    for campo in ("name", "description", "monthly_amount", "currency", "criterion", "is_active"):
        if campo in datos and datos[campo] is not None:
            setattr(s, campo, datos[campo])
    if "fixed_shares" in datos:
        s.fixed_shares = json.dumps({str(k): float(v) for k, v in (datos["fixed_shares"] or {}).items()})
    if s.criterion == "fijo":
        suma = round(sum(_cuotas_fijas(s).values()), 2)
        if abs(suma - 100) > 0.01:
            raise error(422, "interno_reparto_fijo_no_suma", suma=suma)
    db.add(s)
    db.flush()
    audit_log(db, actor, "UPDATE" if sid else "CREATE", "internal_shared_cost", s.id, s.name,
              old_values=antes, new_values=servicio_dict(s))
    db.commit()
    return servicio_dict(s)


def borrar_servicio(db: Session, actor, sid: str) -> None:
    from app.services.audit import audit_log
    s = _servicio_o_404(db, sid)
    audit_log(db, actor, "DELETE", "internal_shared_cost", s.id, s.name, old_values=servicio_dict(s))
    db.delete(s)
    db.commit()


def reparto_de_servicio(db: Session, actor, sid: str, texto_periodo: str) -> dict:
    desde, hasta = periodo(texto_periodo)
    r = reparto(db, _servicio_o_404(db, sid), desde, hasta, actor)
    r["period"] = texto_periodo
    return r
