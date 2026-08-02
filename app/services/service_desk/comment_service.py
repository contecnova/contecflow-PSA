from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.service_desk import Ticket, TicketComment, TicketStatus
from app.models.user import User
from app.services.service_desk.scoping import scope_ticket_query as _scope_ticket_query
import logging

logger = logging.getLogger(__name__)


def get_scoped_ticket_or_404(db: Session, current_user: Optional[User], ticket_id: str) -> Ticket:
    ticket = _scope_ticket_query(db.query(Ticket), db, current_user).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(404)
    return ticket


def add_internal_comment(
    db: Session,
    ticket: Ticket,
    ticket_id: str,
    body: str,
    is_public: bool,
    current_user: Optional[User],
) -> TicketComment:
    comment = TicketComment(
        ticket_id=ticket_id,
        body=body,
        is_public=is_public,
        author_user_id=current_user.id if current_user else None,
    )
    db.add(comment)

    if not ticket.first_response_at and current_user and is_public:
        ticket.first_response_at = datetime.now(timezone.utc)
        if ticket.status == TicketStatus.new:
            ticket.status = TicketStatus.in_progress

    return comment


def get_client_ticket_or_404(db: Session, ticket_id: str, client_id: str) -> Ticket:
    """Ticket acotado al cliente de portal solicitante.

    client_id es OBLIGATORIO: sin este filtro cualquier cliente autenticado del
    portal podría comentar (is_public=True) en el ticket de otro cliente (IDOR).
    404 en lugar de 403 para no revelar la existencia del ticket ajeno.
    """
    ticket = (
        db.query(Ticket)
        .filter(Ticket.id == ticket_id, Ticket.requester_client_id == client_id)
        .first()
    )
    if not ticket:
        raise HTTPException(404, "Ticket no encontrado")
    return ticket


def add_client_comment(db: Session, ticket: Ticket, ticket_id: str, body: str, client_id: str) -> TicketComment:
    comment = TicketComment(
        ticket_id=ticket_id,
        body=body,
        is_public=True,
        author_client_id=client_id,
    )
    db.add(comment)

    if ticket.status == TicketStatus.pending_client:
        ticket.status = TicketStatus.in_progress
        if ticket.sla_paused_at:
            paused_at = ticket.sla_paused_at
            if paused_at.tzinfo is None:
                paused_at = paused_at.replace(tzinfo=timezone.utc)
            paused_minutes = int((datetime.now(timezone.utc) - paused_at).total_seconds() / 60)
            ticket.sla_pause_minutes = (ticket.sla_pause_minutes or 0) + paused_minutes
            ticket.sla_paused_at = None

    return comment
