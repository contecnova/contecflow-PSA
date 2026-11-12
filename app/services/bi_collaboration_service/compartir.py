"""Comparticion de paneles con usuarios y sus permisos.

Parte de `app.services.bi_collaboration_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from sqlalchemy.orm import Session
from app.models.bi_collaboration import DashboardShare
from app.models.user import User

from app.services.bi_collaboration_service._comun import (
    SHARES_KEY_PREFIX,
    _emit_dashboard_notification,
)


SHARE_PERMISSIONS = {"view", "edit", "admin"}


# ── Dashboard Sharing ─────────────────────────────────────────────────────────

def _shares_key(dashboard_key: str) -> str:
    return f"{SHARES_KEY_PREFIX}{dashboard_key}"


def list_dashboard_shares(
    db: Session,
    *,
    organization_id: Optional[str],
    dashboard_key: str,
) -> list[dict[str, Any]]:
    q = db.query(DashboardShare).filter(DashboardShare.dashboard_key == dashboard_key)
    if organization_id:
        q = q.filter(DashboardShare.organization_id == organization_id)
    else:
        q = q.filter(DashboardShare.organization_id.is_(None))
    rows = q.order_by(DashboardShare.created_at.desc()).all()
    return [
        {
            "id": r.id,
            "dashboard_key": r.dashboard_key,
            "user_id": r.user_id,
            "user_name": r.user_name,
            "permission": r.permission,
            "shared_by_id": r.shared_by_id,
            "shared_by_name": r.shared_by_name,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in rows
    ]


def share_dashboard(
    db: Session,
    *,
    organization_id: Optional[str],
    dashboard_key: str,
    target_user_id: str,
    target_user_name: str,
    permission: str,
    shared_by: User,
) -> dict[str, Any]:
    if permission not in SHARE_PERMISSIONS:
        raise ValueError("invalid_permission")
    q = db.query(DashboardShare).filter(
        DashboardShare.dashboard_key == dashboard_key,
        DashboardShare.user_id == target_user_id,
    )
    if organization_id:
        q = q.filter(DashboardShare.organization_id == organization_id)
    else:
        q = q.filter(DashboardShare.organization_id.is_(None))
    row = q.first()
    now = datetime.now(timezone.utc)
    if row:
        row.permission = permission
        row.updated_at = now
        row.user_name = target_user_name
    else:
        row = DashboardShare(
            organization_id=organization_id,
            dashboard_key=dashboard_key,
            user_id=target_user_id,
            user_name=target_user_name,
            permission=permission,
            shared_by_id=shared_by.id,
            shared_by_name=shared_by.full_name,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    _emit_dashboard_notification(
        db,
        organization_id=organization_id,
        dashboard_key=dashboard_key,
        event_type="share_updated",
        payload={"user_id": target_user_id, "permission": permission, "shared_by": shared_by.id},
        recipient_user_id=target_user_id,
    )
    db.commit()
    return {
        "id": row.id,
        "dashboard_key": row.dashboard_key,
        "user_id": row.user_id,
        "user_name": row.user_name,
        "permission": row.permission,
        "shared_by_id": row.shared_by_id,
        "shared_by_name": row.shared_by_name,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def revoke_dashboard_share(
    db: Session,
    *,
    organization_id: Optional[str],
    dashboard_key: str,
    share_id: str,
) -> bool:
    q = db.query(DashboardShare).filter(
        DashboardShare.id == share_id,
        DashboardShare.dashboard_key == dashboard_key,
    )
    if organization_id:
        q = q.filter(DashboardShare.organization_id == organization_id)
    else:
        q = q.filter(DashboardShare.organization_id.is_(None))
    row = q.first()
    if row is None:
        return False
    target_user_id = row.user_id
    db.delete(row)
    _emit_dashboard_notification(
        db,
        organization_id=organization_id,
        dashboard_key=dashboard_key,
        event_type="share_revoked",
        payload={"share_id": share_id, "user_id": target_user_id},
        recipient_user_id=target_user_id,
    )
    db.commit()
    return True
