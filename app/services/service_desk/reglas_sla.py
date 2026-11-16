"""SLA condicionales y OLA por prioridad (mejoras de mercado 16-11-2026, migracion 174).

**SLA condicionales** (`sd_sla_rules`). Antes el plazo salia solo de la
politica (contrato, cliente o por defecto) y la prioridad. Ahora una empresa
declara reglas: la primera activa (por `sort_order`) cuyas condiciones encajan
—servicio del catalogo, tipo de ticket, cliente, contrato y prioridad; vacio es
«cualquiera»— fija las horas de respuesta y de resolucion. Si la regla no fija
una de las dos, esa sale de la politica. La regla puede fijar tambien el
calendario (el de su politica); si no, el de la politica del ticket.

Se aplica al abrir el ticket y cada vez que se recalculan sus plazos (cambio
de prioridad, matriz de urgencia e impacto…), siempre desde la apertura.

**OLA por prioridad** (`sd_ola_targets`). El OLA de una cola era un unico
objetivo (`sd_agent_groups.ola_hours`). Ahora se puede fijar por prioridad;
sin fila para la prioridad del ticket, vale el de la cola.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.service_desk import OLATarget, SLAPolicy, SLARule, Ticket
from app.core.errores import ErrorDeDominio

PRIORIDADES = ("p1_critical", "p2_high", "p3_medium", "p4_low")
TIPOS_DE_TICKET = ("incident", "service_request", "change", "problem", "question")


def _v(x):
    return getattr(x, "value", x)


def regla_que_aplica(db: Session, ticket: Ticket) -> Optional[SLARule]:
    q = db.query(SLARule).filter(SLARule.is_active.is_(True))
    if ticket.organization_id is not None:
        q = q.filter(SLARule.organization_id == ticket.organization_id)
    datos = {
        "service_item_id": ticket.service_item_id, "ticket_type": _v(ticket.ticket_type),
        "client_id": ticket.client_id, "contract_id": ticket.contract_id, "priority": _v(ticket.priority),
    }
    for regla in q.order_by(SLARule.sort_order, SLARule.created_at).all():
        if all(getattr(regla, campo) in (None, "") or getattr(regla, campo) == valor for campo, valor in datos.items()):
            return regla
    return None


def aplicar_regla(db: Session, ticket: Ticket) -> Optional[SLARule]:
    """Fija los plazos del ticket con la regla que encaja, desde su apertura. Devuelve la regla."""
    from app.services.sla_service import calculate_sla_due

    regla = regla_que_aplica(db, ticket)
    if regla is None or (regla.response_hours is None and regla.resolution_hours is None):
        return None
    politica = db.get(SLAPolicy, regla.sla_policy_id) if regla.sla_policy_id else (
        db.get(SLAPolicy, ticket.sla_policy_id) if ticket.sla_policy_id else None)
    prioridad = _v(ticket.priority)
    base_resp, base_res = calculate_sla_due(prioridad, politica, db=db, org_id=ticket.organization_id,
                                           start=ticket.created_at)
    if regla.response_hours is not None and regla.resolution_hours is not None:
        horas = (float(regla.response_hours), float(regla.resolution_hours))
        resp, res = calculate_sla_due(prioridad, politica, db=db, org_id=ticket.organization_id,
                                      start=ticket.created_at, hours=horas)
    else:
        # Solo uno de los dos objetivos: el otro, el de la politica.
        horas_resp = float(regla.response_hours) if regla.response_hours is not None else None
        horas_res = float(regla.resolution_hours) if regla.resolution_hours is not None else None
        ref = horas_resp if horas_resp is not None else horas_res
        resp, res = calculate_sla_due(prioridad, politica, db=db, org_id=ticket.organization_id,
                                      start=ticket.created_at, hours=(ref, ref))
        resp = resp if horas_resp is not None else base_resp
        res = res if horas_res is not None else base_res
    ticket.sla_response_due, ticket.sla_resolution_due = resp, res
    if regla.sla_policy_id:
        ticket.sla_policy_id = regla.sla_policy_id
    return regla


def horas_de_ola(db: Session, grupo, prioridad) -> Optional[float]:
    """Objetivo del OLA de la cola para esa prioridad; sin fila, el de la cola."""
    if grupo is None:
        return None
    fila = db.query(OLATarget.hours).filter(OLATarget.group_id == grupo.id,
                                            OLATarget.priority == _v(prioridad)).first()
    if fila is not None:
        return float(fila[0])
    return float(grupo.ola_hours) if getattr(grupo, "ola_hours", None) else None


# ── Mantenimiento (API) ───────────────────────────────────────────────────────

_CAMPOS = ("name", "is_active", "sort_order", "service_item_id", "ticket_type", "client_id", "contract_id",
           "priority", "response_hours", "resolution_hours", "sla_policy_id")


def serializar_regla(r: SLARule) -> dict:
    return {c: getattr(r, c) for c in ("id",) + _CAMPOS}


def _validar(datos: dict) -> dict:
    if datos.get("priority") not in (None, "") and datos["priority"] not in PRIORIDADES:
        raise ErrorDeDominio(422, "Prioridad no válida")
    if datos.get("ticket_type") not in (None, "") and datos["ticket_type"] not in TIPOS_DE_TICKET:
        raise ErrorDeDominio(422, "Tipo de ticket no válido")
    for h in ("response_hours", "resolution_hours"):
        if datos.get(h) is not None and float(datos[h]) <= 0:
            raise ErrorDeDominio(422, "Las horas tienen que ser mayores que cero")
    if datos.get("response_hours") is None and datos.get("resolution_hours") is None and "name" in datos:
        raise ErrorDeDominio(422, "Una regla fija al menos un objetivo")
    return {k: (None if v == "" else v) for k, v in datos.items() if k in _CAMPOS}


def listar_reglas(db: Session, org_id) -> list[dict]:
    q = db.query(SLARule).filter(SLARule.organization_id == org_id)
    return [serializar_regla(r) for r in q.order_by(SLARule.sort_order, SLARule.created_at).all()]


def guardar_regla(db: Session, org_id, datos: dict, regla_id: Optional[str] = None) -> dict:
    datos = _validar(datos)
    if regla_id:
        regla = db.query(SLARule).filter(SLARule.id == regla_id, SLARule.organization_id == org_id).first()
        if regla is None:
            raise ErrorDeDominio(404, "Regla no encontrada")
    else:
        regla = SLARule(organization_id=org_id)
        db.add(regla)
    for k, v in datos.items():
        setattr(regla, k, v)
    db.commit()
    return serializar_regla(regla)


def borrar_regla(db: Session, org_id, regla_id: str) -> None:
    n = db.query(SLARule).filter(SLARule.id == regla_id, SLARule.organization_id == org_id).delete()
    if not n:
        raise ErrorDeDominio(404, "Regla no encontrada")
    db.commit()


def ola_de_la_cola(db: Session, org_id, group_id: str) -> dict:
    from app.models.service_desk import AgentGroup
    grupo = db.query(AgentGroup).filter(AgentGroup.id == group_id, AgentGroup.organization_id == org_id).first()
    if grupo is None:
        raise ErrorDeDominio(404, "Cola no encontrada")
    filas = {f.priority: f.hours for f in db.query(OLATarget).filter(OLATarget.group_id == group_id)}
    return {"group_id": group_id, "default_hours": grupo.ola_hours,
            "targets": {p: filas.get(p) for p in PRIORIDADES}}


def guardar_ola(db: Session, org_id, group_id: str, objetivos: dict) -> dict:
    ola_de_la_cola(db, org_id, group_id)  # 404 si no es de la empresa
    for prioridad, horas in (objetivos or {}).items():
        if prioridad not in PRIORIDADES:
            raise ErrorDeDominio(422, "Prioridad no válida")
        fila = db.query(OLATarget).filter(OLATarget.group_id == group_id, OLATarget.priority == prioridad).first()
        if horas in (None, ""):
            if fila is not None:
                db.delete(fila)
            continue
        if float(horas) <= 0:
            raise ErrorDeDominio(422, "Las horas tienen que ser mayores que cero")
        if fila is None:
            db.add(OLATarget(organization_id=org_id, group_id=group_id, priority=prioridad, hours=float(horas)))
        else:
            fila.hours = float(horas)
    db.commit()
    return ola_de_la_cola(db, org_id, group_id)
