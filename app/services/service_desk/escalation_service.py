import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.models.service_desk import (
    EscalationAction,
    EscalationLog,
    EscalationRule,
    EscalationTrigger,
    Ticket,
    TicketPriority,
    TicketStatus,
)
from app.schemas.service_desk import EscalationRuleIn


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
        "trigger": rule.trigger,
        "action": rule.action,
        "applies_to_priority": rule.applies_to_priority,
        "idle_hours_threshold": rule.idle_hours_threshold,
        "group_id": rule.group_id,
        "target_group_id": rule.target_group_id,
        "notify_user_ids": rule.notify_user_ids,
        "target_priority": rule.target_priority,
    }


def validate_escalation_rule(payload: EscalationRuleIn) -> None:
    try:
        EscalationTrigger(payload.trigger)
        EscalationAction(payload.action)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


def build_escalation_rule(payload: EscalationRuleIn) -> EscalationRule:
    return EscalationRule(**payload.model_dump())


def create_escalation_rule_record(db, payload: EscalationRuleIn) -> EscalationRule:
    validate_escalation_rule(payload)
    rule = build_escalation_rule(payload)
    db.add(rule)
    return rule


def get_escalation_rule_by_id(db: Session, rule_id: str) -> EscalationRule:
    rule = db.query(EscalationRule).filter(EscalationRule.id == rule_id).first()
    if not rule:
        raise HTTPException(404)
    return rule


def apply_escalation_rule_update(rule: EscalationRule, payload: EscalationRuleIn) -> None:
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(rule, key, value)


def update_escalation_rule_record(db: Session, rule_id: str, payload: EscalationRuleIn) -> EscalationRule:
    rule = get_escalation_rule_by_id(db, rule_id)
    apply_escalation_rule_update(rule, payload)
    return rule


def get_escalation_rule_for_delete(db: Session, rule_id: str) -> EscalationRule:
    return get_escalation_rule_by_id(db, rule_id)


def delete_escalation_rule(db: Session, rule_id: str) -> None:
    rule = get_escalation_rule_by_id(db, rule_id)
    db.delete(rule)


def _parse_priority_filter(raw_priority_filter: Optional[str]):
    if not raw_priority_filter:
        return None
    try:
        return json.loads(raw_priority_filter)
    except Exception:
        return [raw_priority_filter]


def _ticket_is_open(ticket: Ticket) -> bool:
    return ticket.status not in [TicketStatus.resolved, TicketStatus.closed, TicketStatus.cancelled]


def _should_fire_rule(rule: EscalationRule, ticket: Ticket, now: datetime) -> bool:
    priority_filter = _parse_priority_filter(rule.applies_to_priority)

    if priority_filter and ticket.priority.value not in priority_filter:
        return False
    if rule.group_id and ticket.assigned_group_id != rule.group_id:
        return False

    if rule.trigger == EscalationTrigger.sla_at_risk and ticket.sla_resolution_status == "at_risk":
        return True
    if rule.trigger == EscalationTrigger.sla_breached and ticket.sla_resolution_status == "breached":
        return True
    if rule.trigger == EscalationTrigger.idle_hours and rule.idle_hours_threshold:
        last_activity = ticket.updated_at or ticket.created_at
        if last_activity:
            idle_hours = (now - last_activity).total_seconds() / 3600
            return idle_hours >= rule.idle_hours_threshold
    if rule.trigger == EscalationTrigger.priority and not ticket.assigned_to_user_id:
        return True

    return False


def _already_fired_recently(db: Session, rule_id: str, ticket_id: str, now: datetime) -> bool:
    recent = db.query(EscalationLog).filter(
        EscalationLog.rule_id == rule_id,
        EscalationLog.ticket_id == ticket_id,
        EscalationLog.triggered_at >= now - timedelta(hours=1),
    ).first()
    return recent is not None


def _apply_rule_action(rule: EscalationRule, ticket: Ticket) -> str:
    action_desc = f"Rule '{rule.name}' fired: {rule.action}"
    if rule.action == EscalationAction.reassign_group and rule.target_group_id:
        ticket.assigned_group_id = rule.target_group_id
        action_desc += f" -> group {rule.target_group_id}"
    elif rule.action == EscalationAction.elevate_priority and rule.target_priority:
        old_priority = ticket.priority.value
        ticket.priority = TicketPriority(rule.target_priority)
        action_desc += f" {old_priority} -> {rule.target_priority}"
    return action_desc


def run_escalation_rules_engine(db: Session) -> dict:
    now = datetime.now(timezone.utc)
    rules = (
        db.query(EscalationRule)
        .filter(EscalationRule.is_active == True)
        .order_by(EscalationRule.sort_order)
        .all()
    )
    open_tickets = db.query(Ticket).all()
    open_tickets = [t for t in open_tickets if _ticket_is_open(t)]

    fired = 0
    for rule in rules:
        for ticket in open_tickets:
            if not _should_fire_rule(rule, ticket, now):
                continue
            if _already_fired_recently(db, rule.id, ticket.id, now):
                continue

            action_desc = _apply_rule_action(rule, ticket)
            db.add(EscalationLog(rule_id=rule.id, ticket_id=ticket.id, action_taken=action_desc))
            fired += 1

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
