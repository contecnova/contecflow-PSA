"""Servicios gestionados de un proveedor y su SLA medido en su cola del service desk.

Los tickets cuyo `assigned_group_id` es la cola del servicio son del proveedor.
Del periodo cuentan los resueltos (`resolved_at` en el periodo). Con plazos
propios del servicio (`sla_response_hours`, `sla_resolution_hours`) se miden
contra `first_response_at` / `resolved_at` (descontando la pausa del SLA); sin
ellos, con las marcas de incumplimiento del SLA del ticket.
"""
from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.services.audit import audit_log
from app.services.proveedores import serializar as ser


def exigir(db: Session, servicio_id: str):
    from app.models.proveedores import SupplierService
    s = db.query(SupplierService).filter(SupplierService.id == servicio_id).first()
    if s is None:
        raise error(404, "no_encontrado", detail="Servicio no encontrado", que="servicio")
    return s


def listar(db: Session, sub_id: str) -> list:
    from app.models.proveedores import SupplierService
    return [ser.servicio(s) for s in db.query(SupplierService).filter(SupplierService.subcontractor_id == sub_id)
            .order_by(SupplierService.name).all()]


def _json(datos: dict) -> dict:
    for k in ("kpis", "credit_rules", "bonus_rules"):
        if datos.get(k) is not None:
            datos[k] = [x if isinstance(x, dict) else x.model_dump() for x in datos[k]]
    return datos


def _validar(db: Session, s) -> None:
    from app.models.alm import ALMContract
    from app.models.proveedores import SupplierContract
    from app.models.service_desk.agents import AgentGroup
    from app.models.service_desk.catalog import ServiceItem
    from app.services.proveedores import medicion
    if s.agent_group_id and not db.query(AgentGroup.id).filter(AgentGroup.id == s.agent_group_id).first():
        raise error(404, "no_encontrado", detail="Cola no encontrada", que="grupo")
    # Migracion 191: elemento del catalogo del service desk y contrato ALM (UC) elegibles en la ficha.
    if s.service_item_id and not db.query(ServiceItem.id).filter(ServiceItem.id == s.service_item_id).first():
        raise error(404, "no_encontrado", detail="Elemento del catálogo no encontrado", que="elemento_de_catalogo")
    if s.alm_contract_id and not db.query(ALMContract.id).filter(ALMContract.id == s.alm_contract_id).first():
        raise error(404, "no_encontrado", detail="Contrato ALM no encontrado", que="contrato_alm")
    medicion.validar_servicio(db, s)
    if s.contract_id and not db.query(SupplierContract.id).filter(
            SupplierContract.id == s.contract_id, SupplierContract.subcontractor_id == s.subcontractor_id).first():
        raise error(404, "no_encontrado", detail="Contrato no encontrado", que="contrato")
    if s.start_date and s.end_date and s.end_date < s.start_date:
        raise error(422, "proveedor_fechas_no_validas")


def crear(db: Session, sub, datos: dict, actor) -> dict:
    from app.models.proveedores import SupplierService
    from app.services.proveedores import ficha
    from app.services.proveedores.tipos import modos
    ficha.exigir_activo(sub)
    if "managed_services" not in modos(sub):
        raise error(422, "proveedor_sin_modo", modo="managed_services", proveedor=sub.name)
    datos = _json({k: v for k, v in datos.items() if v is not None})
    for campo in ("service_type", "name"):
        if not datos.get(campo):
            raise error(422, "campo_obligatorio", campo=campo)
    s = SupplierService(subcontractor_id=sub.id, status=datos.pop("status", None) or "active", **datos)
    _validar(db, s)
    db.add(s)
    db.flush()
    audit_log(db, actor, "CREATE", "supplier_services", s.id, s.name,
              new_values={"service_type": s.service_type, "agent_group_id": s.agent_group_id,
                          "metering_source": s.metering_source, "metering_config": s.metering_config})
    db.commit()
    db.refresh(s)
    return ser.servicio(s)


def actualizar(db: Session, s, datos: dict, actor) -> dict:
    datos = _json(datos)
    antes = ser.servicio(s)
    for k, v in datos.items():
        setattr(s, k, v)
    _validar(db, s)
    audit_log(db, actor, "UPDATE", "supplier_services", s.id, s.name, old_values={k: antes.get(k) for k in datos},
              new_values={k: (str(v) if hasattr(v, "isoformat") else v) for k, v in datos.items()})
    db.commit()
    db.refresh(s)
    return ser.servicio(s)


def terminar(db: Session, s, actor) -> dict:
    from app.core import timeutil
    s.status = "ended"
    s.end_date = s.end_date if s.end_date and s.end_date <= timeutil.today() else timeutil.today()
    audit_log(db, actor, "UPDATE", "supplier_services", s.id, s.name, new_values={"status": "ended"})
    db.commit()
    return ser.servicio(s)


def _limites(desde: date, hasta: date) -> tuple[datetime, datetime]:
    return (datetime.combine(desde, time.min, tzinfo=timezone.utc),
            datetime.combine(hasta, time.max, tzinfo=timezone.utc))


def _aware(v: Optional[datetime]) -> Optional[datetime]:
    if v is None:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def tickets_resueltos(db: Session, s, desde: date, hasta: date, tipo: Optional[str] = None) -> list:
    from app.models.service_desk.tickets import Ticket
    if not s.agent_group_id:
        return []
    a, b = _limites(desde, hasta)
    q = db.query(Ticket).filter(Ticket.assigned_group_id == s.agent_group_id, Ticket.resolved_at.isnot(None),
                                Ticket.resolved_at >= a, Ticket.resolved_at <= b)
    if tipo:
        q = q.filter(Ticket.ticket_type == tipo)
    return q.all()


def sla(db: Session, s, desde: date, hasta: date) -> dict:
    from app.models.service_desk.tickets import Ticket
    resueltos = tickets_resueltos(db, s, desde, hasta)
    total = 0
    if s.agent_group_id:
        a, b = _limites(desde, hasta)
        total = db.query(Ticket).filter(Ticket.assigned_group_id == s.agent_group_id,
                                        Ticket.created_at >= a, Ticket.created_at <= b).count()
    resp_ok = resp_n = res_ok = 0
    for t in resueltos:
        pausa = (t.sla_pause_minutes or 0) * 60
        creado = _aware(t.created_at)
        if s.sla_resolution_hours and creado:
            res_ok += ((_aware(t.resolved_at) - creado).total_seconds() - pausa) <= s.sla_resolution_hours * 3600
        else:
            res_ok += not bool(t.sla_resolution_breached)
        if s.sla_response_hours and creado:
            if t.first_response_at is not None:
                resp_n += 1
                resp_ok += (_aware(t.first_response_at) - creado).total_seconds() <= s.sla_response_hours * 3600
        else:
            resp_n += 1
            resp_ok += not bool(t.sla_response_breached)
    n = len(resueltos)
    resolucion = round(res_ok / n * 100, 1) if n else None
    respuesta = round(resp_ok / resp_n * 100, 1) if resp_n else None
    objetivo = s.sla_target_pct
    return {
        "service_id": s.id, "period_start": str(desde), "period_end": str(hasta), "tickets_total": total,
        "tickets_resolved": n, "response_met_pct": respuesta, "resolution_met_pct": resolucion,
        "compliance_pct": resolucion, "target_pct": objetivo,
        "met": None if resolucion is None or objetivo is None else resolucion >= objetivo,
        "breaches_response": (resp_n - resp_ok), "breaches_resolution": (n - res_ok),
    }
