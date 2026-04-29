"""
bi_dashboard_collab_service.py — Dashboard collaboration persisted in dedicated DB tables.

Uses ORM models from app.models.bi_collaboration:
  - DashboardComment  — comments + mentions + resolve
  - DashboardShare    — shared view entries
  - DashboardVersion  — layout/filter snapshots with versioning
  - DashboardNotification — reaction/mention notifications

Reactions are stored as lightweight AppSetting JSON (no separate table needed,
volume is low and schema is schemaless by design).
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.bi_collaboration import DashboardComment, DashboardVersion, DashboardShare
from app.models.settings import AppSetting

_KEY_REACTIONS = "bi.collab.reactions"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_reactions(db: Session, org_id: Optional[str]) -> dict:
    q = db.query(AppSetting).filter(AppSetting.key == _KEY_REACTIONS)
    q = q.filter(AppSetting.organization_id == org_id) if org_id else q.filter(AppSetting.organization_id.is_(None))
    row = q.first()
    if not row or not row.value:
        return {}
    try:
        return json.loads(row.value)
    except Exception:
        return {}


def _set_reactions(db: Session, org_id: Optional[str], data: dict) -> None:
    payload = json.dumps(data, ensure_ascii=False)
    q = db.query(AppSetting).filter(AppSetting.key == _KEY_REACTIONS)
    q = q.filter(AppSetting.organization_id == org_id) if org_id else q.filter(AppSetting.organization_id.is_(None))
    row = q.first()
    if not row:
        row = AppSetting(key=_KEY_REACTIONS, organization_id=org_id, value=payload, description="BI dashboard reactions")
        db.add(row)
    else:
        row.value = payload
    db.commit()


def _comment_to_dict(c: DashboardComment) -> dict:
    return {
        "id": c.id,
        "dashboard_id": c.dashboard_key,
        "widget_id": c.widget_id,
        "author_user_id": c.author_id,
        "author_name": c.author_name,
        "text": c.message,
        "resolved": c.resolved,
        "resolved_at": c.resolved_at.isoformat() if c.resolved_at else None,
        "resolved_by": c.resolved_by,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def _version_to_dict(v: DashboardVersion) -> dict:
    return {
        "id": v.id,
        "dashboard_id": v.dashboard_key,
        "version": v.version,
        "config": json.loads(v.config) if v.config else {},
        "change_log": v.change_log,
        "created_by": v.created_by_name,
        "is_public": True,
        "created_at": v.created_at.isoformat() if v.created_at else None,
    }


# ── Comments ──────────────────────────────────────────────────────────────────

def add_comment(
    db: Session,
    *,
    org_id: Optional[str],
    dashboard_id: str,
    widget_id: Optional[str],
    author_user_id: str,
    author_name: str,
    text: str,
    mentions: Optional[list[str]] = None,
) -> dict:
    obj = DashboardComment(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        dashboard_key=dashboard_id,
        widget_id=widget_id or "global",
        message=text,
        author_id=author_user_id,
        author_name=author_name,
        resolved=False,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return _comment_to_dict(obj)


def list_comments(
    db: Session,
    *,
    org_id: Optional[str],
    dashboard_id: Optional[str] = None,
    widget_id: Optional[str] = None,
) -> list[dict]:
    q = db.query(DashboardComment).filter(DashboardComment.organization_id == org_id)
    if dashboard_id:
        q = q.filter(DashboardComment.dashboard_key == dashboard_id)
    if widget_id:
        q = q.filter(DashboardComment.widget_id == widget_id)
    rows = q.order_by(DashboardComment.created_at.desc()).all()
    return [_comment_to_dict(c) for c in rows]


def resolve_comment(db: Session, *, org_id: Optional[str], comment_id: str) -> dict:
    obj = db.query(DashboardComment).filter(
        DashboardComment.id == comment_id,
        DashboardComment.organization_id == org_id,
    ).first()
    if not obj:
        raise ValueError(f"Comment '{comment_id}' not found")
    obj.resolved = True
    obj.resolved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(obj)
    return _comment_to_dict(obj)


# ── Shared views (DashboardVersion) ──────────────────────────────────────────

def save_shared_view(
    db: Session,
    *,
    org_id: Optional[str],
    name: str,
    dashboard_id: str,
    layout_state: dict,
    filter_state: dict,
    created_by: str,
    is_public: bool = False,
) -> dict:
    # Determine next version number
    last = (
        db.query(DashboardVersion)
        .filter(DashboardVersion.organization_id == org_id, DashboardVersion.dashboard_key == dashboard_id)
        .order_by(DashboardVersion.version.desc())
        .first()
    )
    next_ver = (last.version + 1) if last else 1
    config_payload = json.dumps({"layout": layout_state, "filters": filter_state, "name": name, "is_public": is_public}, ensure_ascii=False)
    obj = DashboardVersion(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        dashboard_key=dashboard_id,
        version=next_ver,
        config=config_payload,
        change_log=name,
        created_by_name=created_by,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return _version_to_dict(obj)


def list_shared_views(db: Session, *, org_id: Optional[str], dashboard_id: Optional[str] = None) -> list[dict]:
    q = db.query(DashboardVersion).filter(DashboardVersion.organization_id == org_id)
    if dashboard_id:
        q = q.filter(DashboardVersion.dashboard_key == dashboard_id)
    rows = q.order_by(DashboardVersion.created_at.desc()).all()
    return [_version_to_dict(v) for v in rows]


# ── Reactions (lightweight AppSetting JSON) ───────────────────────────────────

def toggle_reaction(
    db: Session,
    *,
    org_id: Optional[str],
    target_id: str,
    target_type: str,
    user_id: str,
    emoji: str,
) -> dict:
    """Toggle a reaction emoji on a comment or widget."""
    reactions: dict = _get_reactions(db, org_id)
    key = f"{target_type}:{target_id}:{emoji}"
    if key not in reactions:
        reactions[key] = {"target_id": target_id, "target_type": target_type, "emoji": emoji, "users": []}
    users: list = reactions[key]["users"]
    if user_id in users:
        users.remove(user_id)
        action = "removed"
    else:
        users.append(user_id)
        action = "added"
    reactions[key]["count"] = len(users)
    _set_reactions(db, org_id, reactions)
    return {"key": key, "emoji": emoji, "count": len(users), "action": action, "users": users}


def get_reactions(db: Session, *, org_id: Optional[str], target_id: str, target_type: str) -> list[dict]:
    reactions: dict = _get_reactions(db, org_id)
    return [r for r in reactions.values() if r["target_id"] == target_id and r["target_type"] == target_type]
