import math
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.models.service_desk import Ticket, TicketComment, TicketHistory
from app.models.user import User
from app.services.service_desk.scoping import scope_ticket_query
from app.services.service_desk.status_compat import normalize_ticket_status, sanitize_legacy_ticket_statuses
from app.services.service_desk.ticket_query_service import build_ticket_list_query


def list_tickets_payload(
    db: Session,
    current_user: User,
    ticket_out,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    ticket_type: Optional[str] = None,
    assigned_to: Optional[str] = None,
    group_id: Optional[str] = None,
    project_id: Optional[str] = None,
    support_level: Optional[str] = None,
    sla_breached: Optional[bool] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 25,
) -> dict:
    sanitize_legacy_ticket_statuses(db)
    query = build_ticket_list_query(
        db=db,
        current_user=current_user,
        status=status,
        priority=priority,
        ticket_type=ticket_type,
        assigned_to=assigned_to,
        group_id=group_id,
        project_id=project_id,
        support_level=support_level,
        sla_breached=sla_breached,
        search=search,
    )

    total = query.count()
    tickets = query.order_by(Ticket.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "tickets": [ticket_out(ticket) for ticket in tickets],
        "total": total,
        "page": page,
        "pages": math.ceil(total / page_size),
    }


def my_queue_payload(db: Session, current_user: User, ticket_out) -> list[dict]:
    sanitize_legacy_ticket_statuses(db)
    tickets = (
        db.query(Ticket)
        .options(
            joinedload(Ticket.requester_user),
            joinedload(Ticket.requester_client),
            joinedload(Ticket.project),
        )
        .filter(
            Ticket.assigned_to_user_id == current_user.id,
            Ticket.status.notin_(["resolved", "closed", "cancelled"]),
        )
        .order_by(Ticket.priority, Ticket.created_at)
        .all()
    )
    return [ticket_out(ticket) for ticket in tickets]


def client_my_tickets_payload(db: Session, client_id: str, ticket_out, status: Optional[str] = None) -> list[dict]:
    sanitize_legacy_ticket_statuses(db)
    query = (
        db.query(Ticket)
        .options(
            joinedload(Ticket.assigned_to),
            joinedload(Ticket.assigned_group),
            joinedload(Ticket.project),
        )
        .filter(Ticket.requester_client_id == client_id)
    )
    normalized_status = normalize_ticket_status(status)
    if normalized_status:
        query = query.filter(Ticket.status == normalized_status)
    return [ticket_out(ticket) for ticket in query.order_by(Ticket.created_at.desc()).all()]


def client_ticket_detail_payload(db: Session, client_id: str, ticket_id: str, ticket_out) -> dict:
    sanitize_legacy_ticket_statuses(db)
    ticket = (
        db.query(Ticket)
        .options(
            joinedload(Ticket.requester_user),
            joinedload(Ticket.requester_client),
            joinedload(Ticket.assigned_to),
            joinedload(Ticket.assigned_group),
            joinedload(Ticket.project),
            joinedload(Ticket.comments).joinedload(TicketComment.author_user),
            joinedload(Ticket.comments).joinedload(TicketComment.author_client),
        )
        .filter(
            Ticket.id == ticket_id,
            Ticket.requester_client_id == client_id,
        )
        .first()
    )

    if not ticket:
        raise HTTPException(404, "Ticket no encontrado")

    return ticket_out(ticket, include_comments=True)


def ticket_detail_payload(db: Session, current_user: User, ticket_id: str, ticket_out) -> dict:
    sanitize_legacy_ticket_statuses(db)
    query = db.query(Ticket).options(
        joinedload(Ticket.requester_user),
        joinedload(Ticket.requester_client),
        joinedload(Ticket.assigned_to),
        joinedload(Ticket.assigned_group),
        joinedload(Ticket.project),
        joinedload(Ticket.ci),
        joinedload(Ticket.comments).joinedload(TicketComment.author_user),
        joinedload(Ticket.comments).joinedload(TicketComment.author_client),
        joinedload(Ticket.history).joinedload(TicketHistory.changed_by),
        joinedload(Ticket.time_logs),
    )

    ticket = scope_ticket_query(query, db, current_user).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(404, "Ticket no encontrado")

    return ticket_out(ticket, include_comments=True)
