from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.service_desk import SLAEvent, SLAEventType, Ticket
import logging
from app.core.errores import ErrorDeDominio

logger = logging.getLogger(__name__)


def get_ticket_or_404(db: Session, ticket_id: str) -> Ticket:
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise ErrorDeDominio(404)
    return ticket


def pause_ticket_sla(db: Session, ticket_id: str, user_id: str, note: str) -> dict:
    ticket = get_ticket_or_404(db, ticket_id)
    if ticket.sla_paused_at:
        raise ErrorDeDominio(400, "SLA ya está pausado")

    ticket.sla_paused_at = datetime.now(timezone.utc)
    if ticket.status.value not in ("resolved", "closed"):
        ticket.status = "pending_client"

    event = SLAEvent(
        ticket_id=ticket_id,
        event_type=SLAEventType.paused,
        note=note or "SLA pausado",
        created_by=user_id,
    )
    db.add(event)
    return {"ok": True, "paused_at": str(ticket.sla_paused_at)}


def pause_ticket_sla_from_payload(db: Session, ticket_id: str, user_id: str, payload: dict) -> dict:
    note = (payload or {}).get("note", "SLA pausado")
    return pause_ticket_sla(db, ticket_id, user_id, note)


def resume_ticket_sla(db: Session, ticket_id: str, user_id: str) -> dict:
    ticket = get_ticket_or_404(db, ticket_id)
    if not ticket.sla_paused_at:
        raise ErrorDeDominio(400, "SLA no está pausado")

    now = datetime.now(timezone.utc)
    paused_at_tz = ticket.sla_paused_at
    if paused_at_tz.tzinfo is None:
        paused_at_tz = paused_at_tz.replace(tzinfo=timezone.utc)

    pause_duration = int((now - paused_at_tz).total_seconds() / 60)
    ticket.sla_pause_minutes = (ticket.sla_pause_minutes or 0) + pause_duration
    ticket.sla_paused_at = None

    if ticket.sla_response_due:
        ticket.sla_response_due += timedelta(minutes=pause_duration)
    if ticket.sla_resolution_due:
        ticket.sla_resolution_due += timedelta(minutes=pause_duration)

    event = SLAEvent(
        ticket_id=ticket_id,
        event_type=SLAEventType.resumed,
        note=f"SLA reanudado — {pause_duration} min pausado",
        created_by=user_id,
    )
    db.add(event)
    return {"ok": True, "paused_minutes": pause_duration}


def list_sla_events(db: Session, ticket_id: str) -> list[dict]:
    events = db.query(SLAEvent).filter(
        SLAEvent.ticket_id == ticket_id
    ).order_by(SLAEvent.created_at).all()
    return [
        {
            "id": e.id,
            "event_type": e.event_type.value,
            "sla_type": e.sla_type,
            "note": e.note,
            "created_at": str(e.created_at),
        }
        for e in events
    ]
