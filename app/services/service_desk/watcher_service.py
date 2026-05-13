from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.models.service_desk import Ticket, TicketWatcher
import logging

logger = logging.getLogger(__name__)


def list_ticket_watchers(db: Session, ticket_id: str):
    return (
        db.query(TicketWatcher)
        .options(joinedload(TicketWatcher.user))
        .filter(TicketWatcher.ticket_id == ticket_id)
        .all()
    )


def serialize_ticket_watcher(watcher: TicketWatcher) -> dict:
    return {
        "id": watcher.id,
        "user_id": watcher.user_id,
        "user_name": watcher.user.full_name if watcher.user else None,
        "user_email": watcher.user.email if watcher.user else None,
        "since": watcher.created_at.isoformat() if watcher.created_at else None,
    }


def ensure_ticket_exists(db: Session, ticket_id: str) -> None:
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(404)


def find_user_watcher(db: Session, ticket_id: str, user_id: str):
    return db.query(TicketWatcher).filter(
        TicketWatcher.ticket_id == ticket_id,
        TicketWatcher.user_id == user_id,
    ).first()


def build_ticket_watcher(ticket_id: str, user_id: str) -> TicketWatcher:
    return TicketWatcher(ticket_id=ticket_id, user_id=user_id)


def get_or_build_ticket_watcher(db: Session, ticket_id: str, user_id: str) -> tuple[TicketWatcher, bool]:
    ensure_ticket_exists(db, ticket_id)
    existing = find_user_watcher(db, ticket_id, user_id)
    if existing:
        return existing, True
    return build_ticket_watcher(ticket_id, user_id), False


def get_ticket_watcher_for_user(db: Session, ticket_id: str, user_id: str):
    return find_user_watcher(db, ticket_id, user_id)


def watch_ticket_command(db: Session, ticket_id: str, user_id: str):
    watcher, already_watching = get_or_build_ticket_watcher(db, ticket_id, user_id)
    if already_watching:
        return {"ok": True, "already_watching": True}
    db.add(watcher)
    return {"ok": True, "id": watcher.id}


def unwatch_ticket_command(db: Session, ticket_id: str, user_id: str):
    watcher = get_ticket_watcher_for_user(db, ticket_id, user_id)
    if watcher:
        db.delete(watcher)
    return {"ok": True}
