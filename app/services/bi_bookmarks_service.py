"""BI Bookmarks service.

Allows users and organizations to save named dashboard states:
- Period (days range)
- Active tab / section
- Widget-level filter configuration (JSON blob)
- Shared / private flag

State persisted in AppSetting JSON, scoped by organization.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.settings import AppSetting
from app.models.user import User

BOOKMARKS_KEY = "bi.bookmarks"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _setting_row(db: Session, key: str, organization_id: Optional[str]) -> Optional[AppSetting]:
    q = db.query(AppSetting).filter(AppSetting.key == key)
    if organization_id:
        q = q.filter(AppSetting.organization_id == organization_id)
    else:
        q = q.filter(AppSetting.organization_id.is_(None))
    return q.first()


def _get_json(db: Session, key: str, organization_id: Optional[str], default: Any) -> Any:
    row = _setting_row(db, key, organization_id)
    if not row or not row.value:
        return default
    try:
        return json.loads(row.value)
    except Exception:
        return default


def _set_json(db: Session, key: str, organization_id: Optional[str], value: Any, description: str) -> None:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    row = _setting_row(db, key, organization_id)
    if not row:
        row = AppSetting(key=key, organization_id=organization_id, description=description, value=payload)
        db.add(row)
    else:
        row.value = payload
    db.commit()


# ── CRUD ───────────────────────────────────────────────────────────────────────

def list_bookmarks(
    db: Session,
    *,
    organization_id: Optional[str],
    user_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    all_bm = _get_json(db, BOOKMARKS_KEY, organization_id, default=[])
    # Return shared + user's own private bookmarks
    if user_id:
        return [b for b in all_bm if b.get("shared") or b.get("created_by") == user_id]
    return all_bm


def create_bookmark(
    db: Session,
    *,
    organization_id: Optional[str],
    payload: dict[str, Any],
    current_user: User,
) -> dict[str, Any]:
    bookmarks = _get_json(db, BOOKMARKS_KEY, organization_id, default=[])
    name = str(payload.get("name", "")).strip()
    if not name:
        raise ValueError("name_required")

    row: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "name": name,
        "description": str(payload.get("description", "")).strip(),
        "period_days": int(payload.get("period_days", 30)),
        "active_tab": str(payload.get("active_tab", "executive")).strip(),
        "filters": payload.get("filters") or {},
        "widget_states": payload.get("widget_states") or {},
        "chart_types": payload.get("chart_types") or {},
        "shared": bool(payload.get("shared", False)),
        "created_by": current_user.id,
        "created_at": _iso_now(),
        "updated_at": _iso_now(),
    }
    bookmarks.append(row)
    _set_json(db, BOOKMARKS_KEY, organization_id, bookmarks, description="BI dashboard bookmarks (JSON)")
    return row


def update_bookmark(
    db: Session,
    *,
    organization_id: Optional[str],
    bookmark_id: str,
    payload: dict[str, Any],
    current_user: User,
) -> dict[str, Any]:
    bookmarks = _get_json(db, BOOKMARKS_KEY, organization_id, default=[])
    target = next((b for b in bookmarks if b.get("id") == bookmark_id), None)
    if not target:
        raise ValueError("bookmark_not_found")
    # Only owner or if shared
    if target.get("created_by") != current_user.id and not target.get("shared"):
        raise ValueError("access_denied")

    for field in ("name", "description", "period_days", "active_tab", "filters",
                  "widget_states", "chart_types", "shared"):
        if field in payload and payload[field] is not None:
            target[field] = payload[field]
    target["updated_at"] = _iso_now()
    _set_json(db, BOOKMARKS_KEY, organization_id, bookmarks, description="BI dashboard bookmarks (JSON)")
    return target


def delete_bookmark(
    db: Session,
    *,
    organization_id: Optional[str],
    bookmark_id: str,
    current_user: User,
) -> bool:
    bookmarks = _get_json(db, BOOKMARKS_KEY, organization_id, default=[])
    target = next((b for b in bookmarks if b.get("id") == bookmark_id), None)
    if not target:
        return False
    if target.get("created_by") != current_user.id:
        raise ValueError("access_denied")
    new_bookmarks = [b for b in bookmarks if b.get("id") != bookmark_id]
    _set_json(db, BOOKMARKS_KEY, organization_id, new_bookmarks, description="BI dashboard bookmarks (JSON)")
    return True


def get_bookmark(
    db: Session,
    *,
    organization_id: Optional[str],
    bookmark_id: str,
    current_user: User,
) -> dict[str, Any]:
    bookmarks = _get_json(db, BOOKMARKS_KEY, organization_id, default=[])
    target = next((b for b in bookmarks if b.get("id") == bookmark_id), None)
    if not target:
        raise ValueError("bookmark_not_found")
    if not target.get("shared") and target.get("created_by") != current_user.id:
        raise ValueError("access_denied")
    return target
