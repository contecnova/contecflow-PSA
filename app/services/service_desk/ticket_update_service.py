from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.service_desk import SLAPolicy, Ticket
from app.models.user import User
from app.schemas.service_desk import TicketUpdateIn
from app.services.service_desk.scoping import scope_ticket_query as _scope_ticket_query
from app.services.sla_service import (
    PRIORITY_MATRIX,
    calculate_sla_due as _calculate_sla_due,
    log_history as _log_history,
    norm_enum as _norm_enum,
)


def get_scoped_ticket_or_404(db: Session, current_user: User, ticket_id: str) -> Ticket:
    ticket = _scope_ticket_query(db.query(Ticket), db, current_user).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(404, "Ticket no encontrado")
    return ticket


def apply_ticket_update(
    db: Session,
    ticket: Ticket,
    ticket_id: str,
    payload: TicketUpdateIn,
    current_user_id: str,
    old_assigned_to: str,
    old_support_level,
) -> dict:
    changes = payload.model_dump(exclude_unset=True)
    for field, new_val in changes.items():
        old_val = getattr(ticket, field, None)
        _log_history(db, ticket_id, field, old_val, new_val, current_user_id)
        setattr(ticket, field, new_val)

    now = datetime.now(timezone.utc)

    def _aware(dt):
        if dt is None:
            return None
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt

    if payload.status:
        if payload.status == "in_progress":
            if not ticket.first_response_at:
                ticket.first_response_at = now
                if ticket.created_at:
                    ticket.first_response_minutes = int(
                        (now - _aware(ticket.created_at)).total_seconds() / 60
                    )
                if ticket.sla_response_due:
                    effective_due = _aware(ticket.sla_response_due) + timedelta(
                        minutes=ticket.sla_pause_minutes or 0
                    )
                    ticket.sla_response_breached = now > effective_due
            if ticket.sla_paused_at:
                paused_at = ticket.sla_paused_at
                if paused_at.tzinfo is None:
                    paused_at = paused_at.replace(tzinfo=timezone.utc)
                paused_mins = int((now - paused_at).total_seconds() / 60)
                ticket.sla_pause_minutes = (ticket.sla_pause_minutes or 0) + paused_mins
                ticket.sla_paused_at = None
        elif payload.status == "resolved":
            ticket.resolved_at = now
            if not ticket.first_response_at:
                ticket.first_response_at = now
                if ticket.created_at:
                    ticket.first_response_minutes = int(
                        (now - _aware(ticket.created_at)).total_seconds() / 60
                    )
            if ticket.created_at:
                ticket.resolution_minutes = int(
                    (now - _aware(ticket.created_at)).total_seconds() / 60
                )
            if ticket.sla_resolution_due:
                effective_due = _aware(ticket.sla_resolution_due) + timedelta(
                    minutes=ticket.sla_pause_minutes or 0
                )
                ticket.sla_resolution_breached = now > effective_due
        elif payload.status == "closed":
            ticket.closed_at = now
            if not ticket.csat_requested_at:
                ticket.csat_requested_at = now
        elif payload.status == "pending_client":
            ticket.sla_paused_at = now
        else:
            if ticket.sla_paused_at:
                paused_at = ticket.sla_paused_at
                if paused_at.tzinfo is None:
                    paused_at = paused_at.replace(tzinfo=timezone.utc)
                paused_mins = int((now - paused_at).total_seconds() / 60)
                ticket.sla_pause_minutes = (ticket.sla_pause_minutes or 0) + paused_mins
                ticket.sla_paused_at = None

    if payload.urgency or payload.impact:
        new_priority = PRIORITY_MATRIX.get(
            (_norm_enum(ticket.urgency), _norm_enum(ticket.impact)),
            "p3_medium",
        )
        if not payload.priority:
            old_priority = ticket.priority
            ticket.priority = new_priority
            if new_priority != old_priority and ticket.status not in ("resolved", "closed", "cancelled"):
                sla_policy = (
                    db.query(SLAPolicy).filter(SLAPolicy.id == ticket.sla_policy_id).first()
                    if ticket.sla_policy_id
                    else None
                )
                resp_due, res_due = _calculate_sla_due(new_priority, sla_policy, db=db)
                ticket.sla_response_due = resp_due
                ticket.sla_resolution_due = res_due

    if payload.tags is not None:
        ticket.tags = payload.tags

    if payload.support_level:
        _log_history(db, ticket_id, "escalation", old_support_level, payload.support_level, current_user_id)

    return {
        "refresh_profile": payload.status in ("resolved", "closed") and bool(ticket.assigned_to_user_id),
        "reassigned": bool(payload.assigned_to_user_id and old_assigned_to and payload.assigned_to_user_id != old_assigned_to),
    }
