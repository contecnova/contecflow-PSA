from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.service_desk import Ticket, TicketComment, TicketTimeLog
from app.models.user import User
from app.services.service_desk.scoping import scope_ticket_query as _scope_ticket_query
from app.services.sla_service import log_history as _log_history


def get_scoped_ticket_or_404(db: Session, current_user: User, ticket_id: str) -> Ticket:
    ticket = _scope_ticket_query(db.query(Ticket), db, current_user).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(404)
    return ticket


def add_ticket_time(db: Session, ticket: Ticket, ticket_id: str, user_id: str, minutes: int, note: Optional[str] = None) -> dict:
    time_log = TicketTimeLog(ticket_id=ticket_id, user_id=user_id, minutes=minutes, note=note)
    db.add(time_log)
    ticket.time_spent_minutes = (ticket.time_spent_minutes or 0) + minutes
    return {"ok": True, "total_minutes": ticket.time_spent_minutes}


def escalate_ticket_level(
    db: Session,
    ticket: Ticket,
    ticket_id: str,
    to_level: str,
    reason: Optional[str],
    current_user_id: str,
) -> dict:
    old_level = ticket.support_level
    ticket.support_level = to_level
    _log_history(db, ticket_id, "support_level", old_level, to_level, current_user_id)
    if reason:
        db.add(
            TicketComment(
                ticket_id=ticket_id,
                body=f"🔺 Escalado a {to_level}: {reason}",
                is_public=False,
                author_user_id=current_user_id,
            )
        )
    return {"ok": True, "from": old_level, "to": to_level}
