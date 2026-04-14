from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.service_desk import Ticket, TicketStatus


def submit_ticket_csat(db: Session, ticket_id: str, score: int, comment: str = None) -> dict:
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(404)
    if ticket.status not in ["resolved", "closed"]:
        raise HTTPException(400, "Solo tickets resueltos")

    ticket.csat_score = score
    ticket.csat_comment = comment
    if ticket.status == "resolved":
        ticket.status = TicketStatus.closed
        ticket.closed_at = datetime.now(timezone.utc)

    return {"ok": True}
