"""Alert log queries and acknowledgment for BI Smart Alerts."""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.user import User

from .constants import LOG_KEY
from .persistence import _get_json, _iso_now, _set_json


def get_alert_log(db: Session, *, organization_id: Optional[str], limit: int = 100) -> list[dict[str, Any]]:
    log = _get_json(db, LOG_KEY, organization_id, default=[])
    return log[-limit:]


def acknowledge_alert(db: Session, *, organization_id: Optional[str], alert_id: str, current_user: User) -> dict[str, Any]:
    log = _get_json(db, LOG_KEY, organization_id, default=[])
    entry = next((e for e in log if e.get("id") == alert_id), None)
    if not entry:
        raise ValueError("alert_not_found")
    entry["acknowledged"] = True
    entry["acknowledged_by"] = current_user.id
    entry["acknowledged_at"] = _iso_now()
    _set_json(db, LOG_KEY, organization_id, log, description="BI Smart Alert log (JSON)")
    return entry
