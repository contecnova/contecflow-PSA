from sqlalchemy import or_, and_
from sqlalchemy.orm import Session, joinedload

from app.models.service_desk import Ticket, TicketLink
import logging
from app.core.errores import ErrorDeDominio

logger = logging.getLogger(__name__)


def get_ticket_links_for_ticket(db: Session, ticket_id: str):
    return db.query(TicketLink).options(
        joinedload(TicketLink.target),
        joinedload(TicketLink.source),
    ).filter(
        or_(TicketLink.source_id == ticket_id, TicketLink.target_id == ticket_id)
    ).all()


def list_ticket_links_payload(db: Session, ticket_id: str) -> list[dict]:
    links = get_ticket_links_for_ticket(db, ticket_id)
    return [serialize_ticket_link(link, ticket_id) for link in links]


def serialize_ticket_link(link: TicketLink, ticket_id: str) -> dict:
    other = link.target if link.source_id == ticket_id else link.source
    return {
        "link_id": link.id,
        "link_type": link.link_type.value,
        "direction": "outbound" if link.source_id == ticket_id else "inbound",
        "ticket_id": other.id,
        "ticket_number": other.number,
        "ticket_title": other.title,
        "ticket_status": other.status.value,
        "ticket_priority": other.priority.value,
    }


def ensure_ticket_exists(db: Session, ticket_id: str, detail: str) -> None:
    if not db.query(Ticket).filter(Ticket.id == ticket_id).first():
        raise ErrorDeDominio(404, detail)


def ensure_link_can_be_created(db: Session, source_id: str, target_id: str) -> None:
    ensure_ticket_exists(db, source_id, "Ticket origen no encontrado")
    ensure_ticket_exists(db, target_id, "Ticket destino no encontrado")

    if source_id == target_id:
        raise ErrorDeDominio(400, "No se puede vincular un ticket consigo mismo")

    existing = db.query(TicketLink).filter(
        or_(
            and_(TicketLink.source_id == source_id, TicketLink.target_id == target_id),
            and_(TicketLink.source_id == target_id, TicketLink.target_id == source_id),
        )
    ).first()
    if existing:
        raise ErrorDeDominio(409, "Ya existe un vínculo entre estos tickets")


def build_ticket_link(source_id: str, target_id: str, link_type: str, created_by: str) -> TicketLink:
    return TicketLink(
        source_id=source_id,
        target_id=target_id,
        link_type=link_type,
        created_by=created_by,
    )


def create_ticket_link_record(db: Session, ticket_id: str, payload: dict, current_user_id: str) -> TicketLink:
    target_id = payload.get("target_id")
    link_type = payload.get("link_type", "relates_to")

    ensure_link_can_be_created(db, ticket_id, target_id)
    lk = build_ticket_link(ticket_id, target_id, link_type, current_user_id)
    db.add(lk)
    return lk


def get_ticket_link_or_404(db: Session, link_id: str) -> TicketLink:
    link = db.query(TicketLink).filter(TicketLink.id == link_id).first()
    if not link:
        raise ErrorDeDominio(404)
    return link


def get_ticket_link_for_delete(db: Session, link_id: str) -> TicketLink:
    return get_ticket_link_or_404(db, link_id)


def delete_ticket_link(db: Session, link_id: str) -> None:
    lk = get_ticket_link_or_404(db, link_id)
    db.delete(lk)
