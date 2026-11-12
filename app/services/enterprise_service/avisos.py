"""Avisos del usuario: listado, lectura y limpieza.

Parte de `app.services.enterprise_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.enterprise import Notification
from datetime import timedelta
from sqlalchemy import func as _func


# ── Notifications ─────────────────────────────────────────────────────────────

def get_my_notifications(current_user, unread_only: bool, page: int, page_size: int, db: Session) -> dict:
    q = db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_active == True,
    )
    if unread_only:
        q = q.filter(Notification.is_read == False)
    total = q.count()
    unread_count = db.query(_func.count(Notification.id)).filter(
        Notification.user_id == current_user.id,
        Notification.is_read == False,
        Notification.is_active == True,
    ).scalar()
    items = q.order_by(Notification.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "total": total, "unread_count": unread_count, "page": page,
        "notifications": [{
            "id": n.id, "type": n.type, "title": n.title, "body": n.body,
            "icon": n.icon, "color": n.color, "resource": n.resource,
            "resource_id": n.resource_id, "action_url": n.action_url,
            "is_read": n.is_read, "read_at": str(n.read_at)[:16] if n.read_at else None,
            "created_at": str(n.created_at)[:16],
        } for n in items],
    }


def mark_all_notifications_read(current_user, db: Session) -> dict:
    now = datetime.now(timezone.utc)
    db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_read == False,
        Notification.is_active == True,
    ).update({"is_read": True, "read_at": now})
    db.commit()
    return {"ok": True}


def mark_notification_read(notif_id: str, current_user, db: Session) -> dict:
    n = db.query(Notification).filter(
        Notification.id == notif_id,
        Notification.user_id == current_user.id,
        Notification.is_active == True,
    ).first()
    if not n:
        raise ValueError("not_found")
    n.is_read = True
    n.read_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}


def clear_old_notifications(current_user, days: int, db: Session) -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    deleted = db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_active == True,
        Notification.is_read == True,
        Notification.created_at < cutoff,
    ).update({"is_active": False}, synchronize_session=False)
    db.commit()
    return {"ok": True, "deleted": deleted, "message": "Notificaciones antiguas eliminadas correctamente"}
