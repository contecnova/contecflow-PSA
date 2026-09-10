from typing import Optional
import json

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.settings import AppSetting
from app.models.service_desk import Ticket, TicketComment, TicketTimeLog
from app.services.sla_service import log_history as _log_history


# La guarda vive en `scoping.py`, junto a `scope_ticket_query`, de la que
# depende. Se reexporta con el mismo nombre para que ningun sitio de llamada
# cambie: estaba copiada literalmente en este modulo y en dos mas.
from app.services.service_desk.scoping import (  # noqa: E402,F401
    get_scoped_ticket_or_404,
)


def _to_minutes(value: int, unit: str) -> int:
    unit_l = (unit or "minutes").strip().lower()
    if unit_l in {"minute", "minutes", "min", "m"}:
        return max(0, int(value))
    if unit_l in {"hour", "hours", "h"}:
        return max(0, int(value) * 60)
    if unit_l in {"day", "days", "d"}:
        return max(0, int(value) * 60 * 8)
    return max(0, int(value))


def add_ticket_time(
    db: Session,
    ticket: Ticket,
    ticket_id: str,
    user_id: str,
    minutes: int,
    description: Optional[str] = None,
    unit: str = "minutes",
) -> dict:
    minutes_norm = _to_minutes(minutes, unit)
    time_log = TicketTimeLog(ticket_id=ticket_id, user_id=user_id, minutes=minutes_norm, description=description)
    db.add(time_log)
    ticket.time_spent_minutes = (ticket.time_spent_minutes or 0) + minutes_norm
    return {"ok": True, "total_minutes": ticket.time_spent_minutes, "logged_minutes": minutes_norm}


def _pending_snapshot_key(ticket_id: str) -> str:
    return f"sd.ticket.pending_snapshot.{ticket_id}"


def save_pending_snapshot(db: Session, ticket: Ticket) -> None:
    snapshot = {
        "status": str(ticket.status.value) if hasattr(ticket.status, "value") else str(ticket.status),
        "assigned_to_user_id": ticket.assigned_to_user_id,
        "assigned_group_id": ticket.assigned_group_id,
        "support_level": str(ticket.support_level.value) if hasattr(ticket.support_level, "value") else str(ticket.support_level),
        "priority": str(ticket.priority.value) if hasattr(ticket.priority, "value") else str(ticket.priority),
    }
    serialized = json.dumps(snapshot, ensure_ascii=False)
    key = _pending_snapshot_key(ticket.id)
    row = db.query(AppSetting).filter(AppSetting.key == key, AppSetting.organization_id == None).first()
    if row:
        row.value = serialized
        row.description = "Ticket pending snapshot"
    else:
        db.add(AppSetting(key=key, organization_id=None, value=serialized, description="Ticket pending snapshot"))


def restore_pending_snapshot(db: Session, ticket: Ticket, current_user_id: str) -> dict:
    key = _pending_snapshot_key(ticket.id)
    row = db.query(AppSetting).filter(AppSetting.key == key, AppSetting.organization_id == None).first()
    if not row or not row.value:
        return {"ok": False, "restored": False, "detail": "No pending snapshot"}

    try:
        snap = json.loads(row.value)
    except Exception:
        snap = {}

    old_status = str(ticket.status.value) if hasattr(ticket.status, "value") else str(ticket.status)
    ticket.status = snap.get("status") or "in_progress"
    ticket.assigned_to_user_id = snap.get("assigned_to_user_id")
    ticket.assigned_group_id = snap.get("assigned_group_id")
    ticket.support_level = snap.get("support_level") or ticket.support_level
    ticket.priority = snap.get("priority") or ticket.priority
    ticket.sla_paused_at = None
    _log_history(db, ticket.id, "status", old_status, str(ticket.status), current_user_id)

    db.delete(row)
    return {"ok": True, "restored": True, "status": str(ticket.status)}


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


# ── Transaction helper ─────────────────────────────────────────────────────────

def commit_or_rollback(db, detail: str = "Error de transacción") -> None:
    import logging as _logging
    _logger = _logging.getLogger(__name__)
    try:
        db.commit()
    except Exception:
        db.rollback()
        _logger.exception("Database transaction failed in service_desk")
        raise HTTPException(500, detail)
