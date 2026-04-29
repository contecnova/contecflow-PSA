"""
bi_dashboard_collab_service.py — Dashboard collaboration persisted in DB.

Stores collaboration events (comments, annotations, shared views snapshots)
in AppSetting JSON per organization until a dedicated ORM model is created.
Tracks:
  - Comments on specific dashboard widgets/panels
  - @mentions in dashboard context
  - Shared view snapshots (layout + filter state)
  - Reaction emojis on dashboard elements
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.settings import AppSetting

_KEY_COMMENTS = "bi.collab.comments"
_KEY_VIEWS = "bi.collab.shared_views"
_KEY_REACTIONS = "bi.collab.reactions"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get(db: Session, key: str, org_id: Optional[str], default: Any) -> Any:
    q = db.query(AppSetting).filter(AppSetting.key == key)
    q = q.filter(AppSetting.organization_id == org_id) if org_id else q.filter(AppSetting.organization_id.is_(None))
    row = q.first()
    if not row or not row.value:
        return default
    try:
        return json.loads(row.value)
    except Exception:
        return default


def _set(db: Session, key: str, org_id: Optional[str], value: Any) -> None:
    payload = json.dumps(value, ensure_ascii=False)
    q = db.query(AppSetting).filter(AppSetting.key == key)
    q = q.filter(AppSetting.organization_id == org_id) if org_id else q.filter(AppSetting.organization_id.is_(None))
    row = q.first()
    if not row:
        row = AppSetting(key=key, organization_id=org_id, value=payload, description=f"BI Collab: {key}")
        db.add(row)
    else:
        row.value = payload
    db.commit()


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
    comments: list = _get(db, _KEY_COMMENTS, org_id, [])
    entry = {
        "id": str(uuid.uuid4()),
        "dashboard_id": dashboard_id,
        "widget_id": widget_id,
        "author_user_id": author_user_id,
        "author_name": author_name,
        "text": text,
        "mentions": mentions or [],
        "created_at": _iso_now(),
        "resolved": False,
    }
    comments.append(entry)
    _set(db, _KEY_COMMENTS, org_id, comments)
    return entry


def list_comments(
    db: Session,
    *,
    org_id: Optional[str],
    dashboard_id: Optional[str] = None,
    widget_id: Optional[str] = None,
) -> list[dict]:
    comments: list = _get(db, _KEY_COMMENTS, org_id, [])
    if dashboard_id:
        comments = [c for c in comments if c["dashboard_id"] == dashboard_id]
    if widget_id:
        comments = [c for c in comments if c.get("widget_id") == widget_id]
    return sorted(comments, key=lambda c: c["created_at"], reverse=True)


def resolve_comment(db: Session, *, org_id: Optional[str], comment_id: str) -> dict:
    comments: list = _get(db, _KEY_COMMENTS, org_id, [])
    for c in comments:
        if c["id"] == comment_id:
            c["resolved"] = True
            c["resolved_at"] = _iso_now()
            _set(db, _KEY_COMMENTS, org_id, comments)
            return c
    raise ValueError(f"Comment '{comment_id}' not found")


# ── Shared views ──────────────────────────────────────────────────────────────

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
    views: list = _get(db, _KEY_VIEWS, org_id, [])
    entry = {
        "id": str(uuid.uuid4()),
        "name": name,
        "dashboard_id": dashboard_id,
        "layout_state": layout_state,
        "filter_state": filter_state,
        "created_by": created_by,
        "is_public": is_public,
        "created_at": _iso_now(),
        "view_count": 0,
    }
    views.append(entry)
    _set(db, _KEY_VIEWS, org_id, views)
    return entry


def list_shared_views(db: Session, *, org_id: Optional[str], dashboard_id: Optional[str] = None) -> list[dict]:
    views: list = _get(db, _KEY_VIEWS, org_id, [])
    if dashboard_id:
        views = [v for v in views if v["dashboard_id"] == dashboard_id]
    return sorted(views, key=lambda v: v["created_at"], reverse=True)


# ── Reactions ─────────────────────────────────────────────────────────────────

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
    reactions: dict = _get(db, _KEY_REACTIONS, org_id, {})
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
    _set(db, _KEY_REACTIONS, org_id, reactions)
    return {"key": key, "emoji": emoji, "count": len(users), "action": action, "users": users}


def get_reactions(db: Session, *, org_id: Optional[str], target_id: str, target_type: str) -> list[dict]:
    reactions: dict = _get(db, _KEY_REACTIONS, org_id, {})
    return [r for r in reactions.values() if r["target_id"] == target_id and r["target_type"] == target_type]
