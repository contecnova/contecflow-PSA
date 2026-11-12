"""Vistas compartidas y versiones de panel.

Parte de `app.services.bi_collaboration_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

import uuid
from typing import Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.bi_collaboration import DashboardVersion
from app.models.user import User

from app.services.bi_collaboration_service._comun import (
    SHARED_VIEWS_KEY,
    VERSIONS_KEY_PREFIX,
    _emit_dashboard_notification,
    _from_json_value,
    _get_json,
    _iso_now,
    _set_json,
    _to_json_value,
)


def list_shared_views(
    db: Session,
    *,
    organization_id: Optional[str],
    only_active: bool = True,
) -> list[dict[str, Any]]:
    views = _get_json(db, SHARED_VIEWS_KEY, organization_id, default=[])
    if only_active:
        views = [v for v in views if v.get("active", True)]
    views.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return views


def create_shared_view(
    db: Session,
    *,
    organization_id: Optional[str],
    name: str,
    dashboard_key: str,
    filters: dict[str, Any] | None,
    created_by: User,
) -> dict[str, Any]:
    views = _get_json(db, SHARED_VIEWS_KEY, organization_id, default=[])
    payload = {
        "id": str(uuid.uuid4()),
        "name": name.strip(),
        "dashboard_key": dashboard_key,
        "filters": filters or {},
        "active": True,
        "created_at": _iso_now(),
        "created_by_id": created_by.id,
        "created_by_name": created_by.full_name,
    }
    views.append(payload)
    _set_json(
        db,
        SHARED_VIEWS_KEY,
        organization_id,
        views,
        description="BI Collaboration shared dashboard views (JSON)",
    )
    return payload


def patch_shared_view(
    db: Session,
    *,
    organization_id: Optional[str],
    view_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    views = _get_json(db, SHARED_VIEWS_KEY, organization_id, default=[])
    target = None
    for v in views:
        if v.get("id") == view_id:
            target = v
            break
    if target is None:
        raise ValueError("shared_view_not_found")

    if "name" in payload and payload["name"] is not None:
        target["name"] = str(payload["name"]).strip()
    if "dashboard_key" in payload and payload["dashboard_key"] is not None:
        target["dashboard_key"] = str(payload["dashboard_key"])
    if "filters" in payload and payload["filters"] is not None:
        target["filters"] = payload["filters"]
    if "active" in payload and payload["active"] is not None:
        target["active"] = bool(payload["active"])

    _set_json(
        db,
        SHARED_VIEWS_KEY,
        organization_id,
        views,
        description="BI Collaboration shared dashboard views (JSON)",
    )
    return target


# ── Dashboard Versioning ───────────────────────────────────────────────────────

def _versions_key(dashboard_key: str) -> str:
    return f"{VERSIONS_KEY_PREFIX}{dashboard_key}"


def list_dashboard_versions(
    db: Session,
    *,
    organization_id: Optional[str],
    dashboard_key: str,
) -> list[dict[str, Any]]:
    q = db.query(DashboardVersion).filter(DashboardVersion.dashboard_key == dashboard_key)
    if organization_id:
        q = q.filter(DashboardVersion.organization_id == organization_id)
    else:
        q = q.filter(DashboardVersion.organization_id.is_(None))
    rows = q.order_by(DashboardVersion.version.desc()).all()
    return [
        {
            "id": r.id,
            "dashboard_key": r.dashboard_key,
            "version": int(r.version or 0),
            "config": _from_json_value(r.config or "{}", {}),
            "change_log": r.change_log,
            "created_by_id": r.created_by_id,
            "created_by_name": r.created_by_name,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


def create_dashboard_version(
    db: Session,
    *,
    organization_id: Optional[str],
    dashboard_key: str,
    config: dict[str, Any],
    change_log: Optional[str],
    current_user: User,
) -> dict[str, Any]:
    q = db.query(func.max(DashboardVersion.version)).filter(DashboardVersion.dashboard_key == dashboard_key)
    if organization_id:
        q = q.filter(DashboardVersion.organization_id == organization_id)
    else:
        q = q.filter(DashboardVersion.organization_id.is_(None))
    max_ver = q.scalar() or 0
    next_version = int(max_ver) + 1

    row = DashboardVersion(
        organization_id=organization_id,
        dashboard_key=dashboard_key,
        version=next_version,
        config=_to_json_value(config or {}),
        change_log=(change_log or "").strip() or f"Versión {next_version}",
        created_by_id=current_user.id,
        created_by_name=current_user.full_name,
    )
    db.add(row)
    _emit_dashboard_notification(
        db,
        organization_id=organization_id,
        dashboard_key=dashboard_key,
        event_type="version_created",
        payload={"version": next_version, "created_by": current_user.id},
    )

    db.flush()
    # Keep last 50 versions per dashboard+organization.
    trim_q = db.query(DashboardVersion).filter(DashboardVersion.dashboard_key == dashboard_key)
    if organization_id:
        trim_q = trim_q.filter(DashboardVersion.organization_id == organization_id)
    else:
        trim_q = trim_q.filter(DashboardVersion.organization_id.is_(None))
    stale = trim_q.order_by(DashboardVersion.version.desc()).offset(50).all()
    for old in stale:
        db.delete(old)
    db.commit()
    return {
        "id": row.id,
        "dashboard_key": row.dashboard_key,
        "version": row.version,
        "config": _from_json_value(row.config or "{}", {}),
        "change_log": row.change_log,
        "created_by_id": row.created_by_id,
        "created_by_name": row.created_by_name,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def restore_dashboard_version(
    db: Session,
    *,
    organization_id: Optional[str],
    dashboard_key: str,
    version_id: str,
    current_user: User,
) -> dict[str, Any]:
    """Restore a previous version by creating a new version with the old config."""
    versions = list_dashboard_versions(db, organization_id=organization_id, dashboard_key=dashboard_key)
    target = next((v for v in versions if v.get("id") == version_id), None)
    if not target:
        raise ValueError("version_not_found")
    return create_dashboard_version(
        db,
        organization_id=organization_id,
        dashboard_key=dashboard_key,
        config=target["config"],
        change_log=f"Restaurado desde v{target['version']}",
        current_user=current_user,
    )
