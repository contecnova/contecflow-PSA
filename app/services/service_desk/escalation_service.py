import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models.service_desk._enums import (
    ESTADOS_DE_TICKET_ABIERTOS, ESTADOS_DE_TICKET_CERRADOS, ESTADOS_DE_TICKET_RESUELTOS,
)
from app.models.service_desk import (
    AgentGroupMember,
    EscalationAction,
    EscalationLog,
    EscalationRule,
    EscalationTrigger,
    Ticket,
    TicketHistory,
    TicketPriority,
    TicketStatus,
)
from app.schemas.service_desk import EscalationRuleIn
from app.services.service_desk.ticket_events import registrar
from app.services.sla_service import aware
import logging
from app.core.errores import ErrorDeDominio
from app.core.codigos_de_error import error

logger = logging.getLogger(__name__)


def list_escalation_rules(db: Session):
    return db.query(EscalationRule).order_by(EscalationRule.sort_order).all()


def list_escalation_rules_payload(db: Session) -> list[dict]:
    rules = list_escalation_rules(db)
    return [serialize_escalation_rule(rule) for rule in rules]


def serialize_escalation_rule(rule: EscalationRule) -> dict:
    return {
        "id": rule.id,
        "name": rule.name,
        "is_active": rule.is_active,
        "sort_order": rule.sort_order,
        "trigger": _v(rule.trigger),
        "action": _v(rule.action),
        "applies_to_priority": rule.applies_to_priority,
        "idle_hours_threshold": rule.idle_hours_threshold,
        "group_id": rule.group_id,
        "target_group_id": rule.target_group_id,
        "notify_user_ids": rule.notify_user_ids,
        "target_priority": rule.target_priority,
    }


def validate_escalation_rule(payload: EscalationRuleIn) -> None:
    """Una regla que se guarda tiene que poder ejecutarse.

    Antes solo se miraban el disparador y la accion, y solo al crear: «mover a
    otra cola» sin cola, «subir prioridad» sin prioridad o «avisar a estas
    personas» sin nadie se guardaban y luego no hacian nada.
    """
    try:
        trigger = EscalationTrigger(payload.trigger)
        action = EscalationAction(payload.action)
    except ValueError as exc:
        raise error(400, "tipo_no_valido", detail=str(exc))
    if trigger == EscalationTrigger.idle_hours and not (payload.idle_hours_threshold or 0) > 0:
        raise error(422, "escalado_sin_horas")
    if action == EscalationAction.reassign_group and not payload.target_group_id:
        raise error(422, "escalado_sin_cola")
    if action == EscalationAction.elevate_priority:
        try:
            TicketPriority(payload.target_priority or "")
        except ValueError:
            raise error(422, "escalado_sin_prioridad")
    if action == EscalationAction.notify_custom:
        try:
            ids = json.loads(payload.notify_user_ids or "[]")
        except ValueError:
            ids = None
        if not isinstance(ids, list) or not ids:
            raise error(422, "escalado_sin_destinatario")
    if payload.applies_to_priority:
        try:
            prioridades = json.loads(payload.applies_to_priority)
            [TicketPriority(p) for p in prioridades]
        except (ValueError, TypeError):
            raise error(422, "prioridad_no_valida", detail="Prioridades inválidas")


def _ids_de_usuarios_de_la_empresa(db: Session, org_id: Optional[str], ids) -> set[str]:
    """De `ids`, los de usuarios de `org_id` (empresa principal o pertenencia)."""
    from app.models.user import User, UserOrganizationMembership
    ids = [str(i) for i in ids if i]
    if not ids or not org_id:
        return set()
    propios = {r[0] for r in db.query(User.id).filter(User.id.in_(ids), User.organization_id == org_id).all()}
    propios |= {r[0] for r in db.query(UserOrganizationMembership.user_id).filter(
        UserOrganizationMembership.user_id.in_(ids), UserOrganizationMembership.organization_id == org_id).all()}
    return propios


def _cola_de_la_empresa(db: Session, org_id: Optional[str], group_id: Optional[str]) -> bool:
    from app.models.service_desk import AgentGroup
    if not group_id or not org_id:
        return False
    return db.query(AgentGroup.id).filter(AgentGroup.id == group_id,
                                          AgentGroup.organization_id == org_id).first() is not None


def validar_destinos_de_la_regla(db: Session, payload: EscalationRuleIn, org_id: Optional[str]) -> None:
    """Cola y personas de la regla, de la empresa (auditoria 2026-11-22, 4.3).

    Antes se guardaba cualquier id: una regla podia mover tickets a la cola de
    otra empresa o avisar a personas de otra empresa con el titulo del ticket.
    """
    if not org_id:
        return
    if payload.target_group_id and not _cola_de_la_empresa(db, org_id, payload.target_group_id):
        raise error(422, "escalado_cola_ajena")
    if payload.group_id and not _cola_de_la_empresa(db, org_id, payload.group_id):
        raise error(422, "escalado_cola_ajena")
    if payload.notify_user_ids:
        ids = {str(i) for i in json.loads(payload.notify_user_ids or "[]") if i}
        if ids - _ids_de_usuarios_de_la_empresa(db, org_id, ids):
            raise error(422, "escalado_destinatario_ajeno")


def build_escalation_rule(payload: EscalationRuleIn) -> EscalationRule:
    return EscalationRule(**payload.model_dump())


def create_escalation_rule_record(db, payload: EscalationRuleIn) -> EscalationRule:
    validate_escalation_rule(payload)
    validar_destinos_de_la_regla(db, payload, db.info.get("organization_id"))
    rule = build_escalation_rule(payload)
    db.add(rule)
    return rule


def get_escalation_rule_by_id(db: Session, rule_id: str) -> EscalationRule:
    rule = db.query(EscalationRule).filter(EscalationRule.id == rule_id).first()
    if not rule:
        raise ErrorDeDominio(404)
    return rule


def apply_escalation_rule_update(rule: EscalationRule, payload: EscalationRuleIn) -> None:
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(rule, key, value)


def update_escalation_rule_record(db: Session, rule_id: str, payload: EscalationRuleIn) -> EscalationRule:
    validate_escalation_rule(payload)
    rule = get_escalation_rule_by_id(db, rule_id)
    validar_destinos_de_la_regla(db, payload, rule.organization_id or db.info.get("organization_id"))
    apply_escalation_rule_update(rule, payload)
    return rule


def delete_escalation_rule(db: Session, rule_id: str) -> None:
    rule = get_escalation_rule_by_id(db, rule_id)
    db.delete(rule)


def _parse_priority_filter(raw_priority_filter: Optional[str]):
    if not raw_priority_filter:
        return None
    try:
        return json.loads(raw_priority_filter)
    except Exception:
        logger.debug("_parse_priority_filter: excepcion ignorada", exc_info=True)
        return [raw_priority_filter]


#: Auditoria 2026-11-22 (§6): la tupla duplicada pasa a la del modelo.
_ABIERTOS = ESTADOS_DE_TICKET_ABIERTOS
_CERRADOS = ESTADOS_DE_TICKET_RESUELTOS


def _v(x):
    return getattr(x, "value", x)


def _fue_reabierto(db: Session, ticket: Ticket) -> bool:
    """Si alguna vez paso de resuelto o cerrado a otro estado.

    El disparador `reopened` existia en el enum y en la pantalla, y nada lo
    evaluaba: una regla «al reabrir, sube la prioridad» no saltaba nunca.
    """
    return db.query(TicketHistory.id).filter(
        TicketHistory.ticket_id == ticket.id,
        TicketHistory.field_name == "status",
        TicketHistory.old_value.in_(list(_CERRADOS)),
        TicketHistory.new_value.notin_(ESTADOS_DE_TICKET_CERRADOS),
    ).first() is not None


def _ultimo_disparo(db: Session, rule_id: str, ticket_id: str) -> Optional[datetime]:
    return db.query(func.max(EscalationLog.triggered_at)).filter(
        EscalationLog.rule_id == rule_id,
        EscalationLog.ticket_id == ticket_id,
    ).scalar()


def _ultimos_disparos(db: Session, rule_ids: list) -> dict:
    """(regla, ticket abierto) → ultimo disparo, en una consulta (antes una por par: N+1)."""
    if not rule_ids:
        return {}
    filas = db.query(EscalationLog.rule_id, EscalationLog.ticket_id, func.max(EscalationLog.triggered_at)).join(
        Ticket, Ticket.id == EscalationLog.ticket_id,
    ).filter(
        EscalationLog.rule_id.in_(rule_ids), Ticket.status.in_(_ABIERTOS),
    ).group_by(EscalationLog.rule_id, EscalationLog.ticket_id).all()
    return {(r, t): m for r, t, m in filas}


_SIN_CONSULTAR = object()


def _should_fire_rule(db: Session, rule: EscalationRule, ticket: Ticket, now: datetime,
                      ultimo=_SIN_CONSULTAR) -> bool:
    """Si la regla salta sobre el ticket en esta pasada.

    Una vez por episodio: el SLA en riesgo o incumplido, el «sin asignar» y la
    reapertura saltan una sola vez por ticket; la inactividad vuelve a saltar
    solo si el ticket sigue parado otras `idle_hours_threshold` horas desde el
    ultimo disparo. Antes cualquier regla repetia cada hora mientras durase la
    condicion, y un SLA incumplido avisaba cada hora para siempre.
    """
    priority_filter = _parse_priority_filter(rule.applies_to_priority)
    if priority_filter and _v(ticket.priority) not in priority_filter:
        return False
    if rule.group_id and ticket.assigned_group_id != rule.group_id:
        return False

    if ultimo is _SIN_CONSULTAR:
        ultimo = _ultimo_disparo(db, rule.id, ticket.id)
    if rule.trigger == EscalationTrigger.idle_hours:
        if not rule.idle_hours_threshold:
            return False
        desde = max(filter(None, [aware(ticket.updated_at), aware(ticket.created_at), aware(ultimo)]))
        return (now - desde).total_seconds() / 3600 >= rule.idle_hours_threshold
    if ultimo is not None:
        return False
    if rule.trigger == EscalationTrigger.sla_at_risk:
        return _v(ticket.sla_resolution_status) == "at_risk"
    if rule.trigger == EscalationTrigger.sla_breached:
        return _v(ticket.sla_resolution_status) == "breached" or bool(ticket.sla_response_breached)
    if rule.trigger == EscalationTrigger.priority:
        return not ticket.assigned_to_user_id
    if rule.trigger == EscalationTrigger.reopened:
        return _fue_reabierto(db, ticket)
    return False


def _destinatarios_de_la_regla(db: Session, rule: EscalationRule, ticket: Ticket) -> list[str]:
    if rule.action == EscalationAction.notify_manager:
        if ticket.assigned_to is not None and ticket.assigned_to.manager_id:
            return [ticket.assigned_to.manager_id]
        return []
    if rule.action == EscalationAction.notify_group_lead:
        group_id = ticket.assigned_group_id or rule.group_id
        if not group_id:
            return []
        return [r[0] for r in db.query(AgentGroupMember.user_id).filter(
            AgentGroupMember.group_id == group_id, AgentGroupMember.is_lead == True,  # noqa: E712
        ).all()]
    if rule.action == EscalationAction.notify_custom:
        try:
            ids = json.loads(rule.notify_user_ids or "[]")
        except ValueError:
            logger.warning("regla de escalado %s con notify_user_ids ilegible", rule.id)
            return []
        # Auditoria 2026-11-22 (4.3): solo personas de la empresa del ticket,
        # aunque la regla se guardase antes de validar los destinos.
        return sorted(_ids_de_usuarios_de_la_empresa(db, ticket.organization_id, ids))
    return []


def _apply_rule_action(db: Session, rule: EscalationRule, ticket: Ticket) -> str:
    """Aplica la accion y anota el evento `escalated`, que avisa y emite el webhook.

    Las tres acciones de aviso no hacian nada: el motor solo reasignaba o
    subia la prioridad, y para el resto dejaba una linea en el registro.
    Auditoria 2026-11-22 (4.3): la reasignacion deja historial y solo mueve a
    una cola de la empresa del ticket.
    """
    action_desc = f"{rule.name}: {_v(rule.action)}"
    if rule.action == EscalationAction.reassign_group and rule.target_group_id:
        if not _cola_de_la_empresa(db, ticket.organization_id, rule.target_group_id):
            logger.warning("regla de escalado %s: cola %s ajena a la empresa del ticket; no se mueve",
                           rule.id, rule.target_group_id)
        elif ticket.assigned_group_id != rule.target_group_id:
            from app.services.sla_service import log_history
            log_history(db, ticket.id, "assigned_group_id", ticket.assigned_group_id, rule.target_group_id)
            ticket.assigned_group_id = rule.target_group_id
            action_desc += f" -> {rule.target_group.name if rule.target_group else rule.target_group_id}"
    elif rule.action == EscalationAction.elevate_priority and rule.target_priority:
        old_priority = _v(ticket.priority)
        from app.services.service_desk.ticket_update_service import cambiar_prioridad
        if cambiar_prioridad(db, ticket, TicketPriority(rule.target_priority)):
            from app.services.sla_service import log_history
            log_history(db, ticket.id, "priority", old_priority, rule.target_priority)
        action_desc += f" {old_priority} -> {rule.target_priority}"
    destinatarios = _destinatarios_de_la_regla(db, rule, ticket)
    registrar(db, ticket, "escalated",
              {"rule": rule.name, "action": action_desc, "recipients": destinatarios},
              actor_user_id=None)
    return action_desc[:255]


def run_escalation_rules_engine(db: Session, ahora: Optional[datetime] = None) -> dict:
    """Evalua las reglas activas sobre los tickets abiertos. No confirma.

    Cada regla solo mira los tickets de su organizacion: la sesion del worker
    no tiene filtro de tenant, y antes una regla de un cliente podia reasignar
    tickets de otro.
    """
    now = ahora or datetime.now(timezone.utc)
    rules = (
        db.query(EscalationRule)
        .filter(EscalationRule.is_active == True)  # noqa: E712
        .order_by(EscalationRule.sort_order)
        .all()
    )
    open_tickets = db.query(Ticket).filter(Ticket.status.in_(_ABIERTOS)).all()
    # Auditoria 2026-11-22 (4.3): tickets por empresa y ultimos disparos en una
    # sola consulta; antes reglas x tickets consultas de `EscalationLog`.
    por_empresa: dict = {}
    for t in open_tickets:
        por_empresa.setdefault(t.organization_id, []).append(t)
    ultimos = _ultimos_disparos(db, [r.id for r in rules])

    fired = 0
    previo = db.info.get("sd_origen")
    db.info["sd_origen"] = "escalation"
    try:
        for rule in rules:
            for ticket in por_empresa.get(rule.organization_id, []):
                if not _should_fire_rule(db, rule, ticket, now, ultimos.get((rule.id, ticket.id))):
                    continue
                action_desc = _apply_rule_action(db, rule, ticket)
                db.add(EscalationLog(
                    organization_id=ticket.organization_id, rule_id=rule.id,
                    ticket_id=ticket.id, action_taken=action_desc, triggered_at=now,
                ))
                db.flush()
                fired += 1
    finally:
        if previo is None:
            db.info.pop("sd_origen", None)
        else:
            db.info["sd_origen"] = previo

    return {
        "ok": True,
        "rules_evaluated": len(rules),
        "tickets_evaluated": len(open_tickets),
        "escalations_fired": fired,
    }


def run_escalation_rules_job(db: Session) -> dict:
    return run_escalation_rules_engine(db)


def list_escalation_logs(db: Session, ticket_id: Optional[str], limit: int):
    q = db.query(EscalationLog).options(
        joinedload(EscalationLog.rule),
        joinedload(EscalationLog.ticket),
    )
    if ticket_id:
        q = q.filter(EscalationLog.ticket_id == ticket_id)
    return q.order_by(EscalationLog.triggered_at.desc()).limit(limit).all()


def list_escalation_logs_payload(db: Session, ticket_id: Optional[str], limit: int) -> list[dict]:
    logs = list_escalation_logs(db, ticket_id, limit)
    return [serialize_escalation_log(log) for log in logs]


def serialize_escalation_log(log: EscalationLog) -> dict:
    return {
        "id": log.id,
        "rule_name": log.rule.name if log.rule else None,
        "ticket_number": log.ticket.number if log.ticket else None,
        "action_taken": log.action_taken,
        "triggered_at": log.triggered_at.isoformat() if log.triggered_at else None,
    }
