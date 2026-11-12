"""Avisos de colaboracion en paneles e instantanea de cambios.

Parte de `app.services.bi_collaboration_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from sqlalchemy.orm import Session
from app.models.bi_collaboration import DashboardNotification

from app.services.bi_collaboration_service._comun import _from_json_value, _iso_now
from app.services.bi_collaboration_service.comentarios import list_comments
from app.services.bi_collaboration_service.compartir import list_dashboard_shares
from app.services.bi_collaboration_service.vistas_y_versiones import list_dashboard_versions


def dashboard_update_snapshot(
    db: Session,
    *,
    organization_id: Optional[str],
    dashboard_key: str,
) -> dict[str, Any]:
    versions = list_dashboard_versions(db, organization_id=organization_id, dashboard_key=dashboard_key)
    comments = list_comments(
        db,
        organization_id=organization_id,
        dashboard_key=dashboard_key,
        include_resolved=False,
    )
    shares = list_dashboard_shares(db, organization_id=organization_id, dashboard_key=dashboard_key)

    latest_version = max((v.get("version", 0) for v in versions), default=0)
    return {
        "type": "bi_dashboard_update",
        "dashboard_key": dashboard_key,
        "timestamp": _iso_now(),
        "latest_version": latest_version,
        "version_count": len(versions),
        "comment_count": len(comments),
        "share_count": len(shares),
        "recent_comments": comments[:5],
    }


def list_notifications(
    db: Session,
    *,
    organization_id: Optional[str],
    recipient_user_id: Optional[str] = None,
    dashboard_key: Optional[str] = None,
    only_unread: bool = True,
) -> list[dict[str, Any]]:
    """List dashboard notifications for a user."""
    q = db.query(DashboardNotification)
    if organization_id:
        q = q.filter(DashboardNotification.organization_id == organization_id)
    else:
        q = q.filter(DashboardNotification.organization_id.is_(None))
    if recipient_user_id:
        q = q.filter(DashboardNotification.recipient_user_id == recipient_user_id)
    if dashboard_key:
        q = q.filter(DashboardNotification.dashboard_key == dashboard_key)
    if only_unread:
        q = q.filter(DashboardNotification.is_read.is_(False))

    rows = q.order_by(DashboardNotification.created_at.desc()).all()
    return [
        {
            "id": r.id,
            "dashboard_key": r.dashboard_key,
            "event_type": r.event_type,
            "recipient_user_id": r.recipient_user_id,
            "payload": _from_json_value(r.payload_json, {}),
            "is_read": bool(r.is_read),
            "read_at": r.read_at.isoformat() if r.read_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


def mark_notification_read(
    db: Session,
    *,
    organization_id: Optional[str],
    notification_id: str,
    recipient_user_id: Optional[str],
    is_read: bool = True,
) -> dict[str, Any]:
    """Mark a notification as read or unread."""
    q = db.query(DashboardNotification).filter(DashboardNotification.id == notification_id)
    if organization_id:
        q = q.filter(DashboardNotification.organization_id == organization_id)
    else:
        q = q.filter(DashboardNotification.organization_id.is_(None))
    if recipient_user_id:
        q = q.filter(DashboardNotification.recipient_user_id == recipient_user_id)

    row = q.first()
    if not row:
        raise ValueError("notification_not_found")

    row.is_read = is_read
    if is_read:
        row.read_at = datetime.now(timezone.utc)
    else:
        row.read_at = None
    db.commit()

    return {
        "id": row.id,
        "dashboard_key": row.dashboard_key,
        "event_type": row.event_type,
        "recipient_user_id": row.recipient_user_id,
        "payload": _from_json_value(row.payload_json, {}),
        "is_read": bool(row.is_read),
        "read_at": row.read_at.isoformat() if row.read_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
