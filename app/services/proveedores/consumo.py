"""Consumo del proveedor: registrado (manual o importado) y medido automaticamente.

Medicion automatica por unidad (claves del catalogo de unidades del sistema):

- `hour` / `day` / `month`: horas imputadas por sus personas en sus
  asignaciones (+ partes manuales sin duplicar, `externos.conciliacion`); dia =
  horas / jornada de la empresa; mes = meses-persona de asignacion activa.
- `ticket` / `incident` / `request`: tickets resueltos en la cola del servicio.
- `device_month` / `user_month`: el ultimo recuento registrado del periodo o,
  sin el, las unidades contratadas del servicio por los meses del periodo.
- Cualquier otra (llamada, unidad propia de la empresa): consumo registrado.
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.services.audit import audit_log
from app.services.proveedores import serializar as ser
from app.services.proveedores.tipos import UNIDADES_HORAS, UNIDADES_RECUENTO, UNIDADES_TICKETS


def meses(desde: date, hasta: date) -> float:
    """Meses del periodo, por fraccion de cada mes natural que toca (un mes natural = 1.0)."""
    if hasta < desde:
        return 0.0
    total = 0.0
    d = desde
    while d <= hasta:
        dias_mes = calendar.monthrange(d.year, d.month)[1]
        fin_mes = date(d.year, d.month, dias_mes)
        tramo_fin = min(fin_mes, hasta)
        total += ((tramo_fin - d).days + 1) / dias_mes
        d = tramo_fin + timedelta(days=1)
    return round(total, 4)


def _solape(a1: Optional[date], a2: Optional[date], desde: date, hasta: date) -> Optional[tuple[date, date]]:
    ini = max(a1 or desde, desde)
    fin = min(a2 or hasta, hasta)
    return (ini, fin) if ini <= fin else None


# ── Consumo registrado ───────────────────────────────────────────────────────

def listar(db: Session, sub_id: str, contrato_id: Optional[str] = None) -> list:
    from app.models.proveedores import SupplierUsageRecord as U
    q = db.query(U).filter(U.subcontractor_id == sub_id)
    if contrato_id:
        q = q.filter(U.contract_id == contrato_id)
    return [ser.consumo(u) for u in q.order_by(U.period_start.desc()).all()]


def registrar(db: Session, sub, datos: dict, actor) -> dict:
    from app.models.proveedores import SupplierContract, SupplierPricingLine, SupplierUsageRecord
    if datos["period_end"] < datos["period_start"]:
        raise error(422, "proveedor_fechas_no_validas")
    if datos.get("contract_id") and not db.query(SupplierContract.id).filter(
            SupplierContract.id == datos["contract_id"], SupplierContract.subcontractor_id == sub.id).first():
        raise error(404, "no_encontrado", detail="Contrato no encontrado", que="contrato")
    if datos.get("pricing_line_id"):
        x = db.get(SupplierPricingLine, datos["pricing_line_id"])
        if x is None or x.contract.subcontractor_id != sub.id:
            raise error(404, "no_encontrado", detail="Línea de precio no encontrada", que="linea_de_precio")
        datos["contract_id"] = datos.get("contract_id") or x.contract_id
        datos["unit"] = datos.get("unit") or x.unit
    u = SupplierUsageRecord(subcontractor_id=sub.id, created_by=actor.id, **datos)
    db.add(u)
    db.flush()
    audit_log(db, actor, "CREATE", "supplier_usage_records", u.id, sub.name,
              new_values={"unit": u.unit, "quantity": u.quantity, "amount": u.amount,
                          "period": f"{u.period_start}/{u.period_end}"})
    db.commit()
    db.refresh(u)
    return ser.consumo(u)


def borrar(db: Session, uso_id: str, actor) -> dict:
    from app.models.proveedores import SupplierUsageRecord
    u = db.query(SupplierUsageRecord).filter(SupplierUsageRecord.id == uso_id).first()
    if u is None:
        raise error(404, "no_encontrado", detail="Consumo no encontrado", que="consumo")
    if u.statement_id:
        raise error(409, "proveedor_consumo_en_estado_de_cuenta")
    audit_log(db, actor, "DELETE", "supplier_usage_records", u.id, None,
              old_values={"unit": u.unit, "quantity": u.quantity, "amount": u.amount})
    db.delete(u)
    db.commit()
    return {"ok": True}


def _registros(db: Session, contrato, linea, desde: date, hasta: date, unidad: Optional[str] = None) -> list:
    from sqlalchemy import or_

    from app.models.proveedores import SupplierUsageRecord as U
    q = db.query(U).filter(U.subcontractor_id == contrato.subcontractor_id, U.period_start >= desde,
                           U.period_end <= hasta)
    if linea is not None:
        q = q.filter(or_(U.pricing_line_id == linea.id,
                         (U.pricing_line_id.is_(None)) & (U.contract_id == contrato.id) & (U.unit == (unidad or linea.unit))))
    elif unidad:
        q = q.filter(U.contract_id == contrato.id, U.unit == unidad)
    return q.order_by(U.period_end).all()


# ── Medicion automatica ──────────────────────────────────────────────────────

def _asignaciones(db: Session, contrato, linea) -> list:
    from app.models.enterprise import SubcontractorAssignment
    q = db.query(SubcontractorAssignment).filter(SubcontractorAssignment.subcontractor_id == contrato.subcontractor_id,
                                                 SubcontractorAssignment.worker_id.isnot(None))
    if linea.rate_id:
        q = q.filter(SubcontractorAssignment.rate_id == linea.rate_id)
    if contrato.project_id:
        q = q.filter(SubcontractorAssignment.project_id == contrato.project_id)
    return q.all()


def horas(db: Session, contrato, linea, desde: date, hasta: date) -> tuple[float, Optional[str], dict]:
    from app.services.externos.conciliacion import _esperado
    asig = _asignaciones(db, contrato, linea)
    if not asig:
        return 0.0, None, {"assignments": 0}
    h_imp, h_man, _ = _esperado(db, contrato.subcontractor_id, asig, desde, hasta)
    proyectos = {a.project_id for a in asig}
    return round(h_imp + h_man, 2), (proyectos.pop() if len(proyectos) == 1 else None), {
        "hours_imputed": round(h_imp, 2), "hours_manual": round(h_man, 2), "assignments": len(asig)}


def meses_persona(db: Session, contrato, linea, desde: date, hasta: date) -> float:
    total = 0.0
    for a in _asignaciones(db, contrato, linea):
        tramo = _solape(a.start_date, a.end_date, desde, hasta)
        if tramo:
            total += meses(*tramo)
    return round(total, 4)


def _servicio_de(db: Session, contrato, linea):
    from app.models.proveedores import SupplierService
    if linea.service_id:
        return db.get(SupplierService, linea.service_id)
    servicios = db.query(SupplierService).filter(SupplierService.contract_id == contrato.id).all()
    return servicios[0] if len(servicios) == 1 else None


def medir(db: Session, contrato, linea, desde: date, hasta: date, unidad: Optional[str] = None) -> dict:
    """Cantidad de la unidad en el periodo: {quantity, source, detail, project_id, warning}."""
    from app.services.proveedores import servicios as srv
    from app.services.settings_service.por_empresa import jornada_de_empresa
    unidad = unidad or linea.unit
    registros = _registros(db, contrato, linea, desde, hasta, unidad)
    if registros and unidad not in UNIDADES_HORAS + UNIDADES_TICKETS:
        if unidad in UNIDADES_RECUENTO:
            return {"quantity": float(registros[-1].quantity or 0) * meses(desde, hasta), "source": "usage",
                    "detail": {"records": len(registros), "units": registros[-1].quantity}, "project_id": None}
        return {"quantity": round(sum(float(r.quantity or 0) for r in registros), 4), "source": "usage",
                "detail": {"records": len(registros)}, "project_id": registros[-1].project_id}
    if unidad in ("hour", "day"):
        h, pid, det = horas(db, contrato, linea, desde, hasta)
        if unidad == "day":
            jornada = float(jornada_de_empresa(db, registro=contrato) or 8.0) or 8.0
            det["hours_per_day"] = jornada
            h = round(h / jornada, 4)
        return {"quantity": h, "source": "hours", "detail": det, "project_id": pid}
    if unidad == "month":
        return {"quantity": meses_persona(db, contrato, linea, desde, hasta), "source": "hours",
                "detail": {"person_months": True}, "project_id": contrato.project_id}
    if unidad in UNIDADES_TICKETS:
        s = _servicio_de(db, contrato, linea)
        if s is None or not s.agent_group_id:
            return {"quantity": 0.0, "source": "tickets", "detail": {}, "project_id": None, "warning": "sin_cola"}
        tipo = {"incident": "incident", "request": "service_request"}.get(unidad)
        n = len(srv.tickets_resueltos(db, s, desde, hasta, tipo))
        return {"quantity": float(n), "source": "tickets", "detail": {"service_id": s.id}, "project_id": None}
    if unidad in UNIDADES_RECUENTO:
        s = _servicio_de(db, contrato, linea)
        if s is not None and s.contracted_units:
            return {"quantity": round(float(s.contracted_units) * meses(desde, hasta), 4),
                    "source": "contracted_units", "detail": {"service_id": s.id, "units": s.contracted_units},
                    "project_id": None}
    return {"quantity": 0.0, "source": "usage", "detail": {}, "project_id": None,
            "warning": None if registros else "sin_medicion"}
