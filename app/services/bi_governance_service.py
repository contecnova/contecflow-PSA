from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.settings import AppSetting
from app.models.user import User
import logging

logger = logging.getLogger(__name__)

FIELD_SENSITIVITY_KEY = "bi.governance.field_sensitivity"
LINEAGE_KEY = "bi.governance.data_lineage"


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
    if row is None:
        row = AppSetting(key=key, organization_id=organization_id, value=payload, description=description)
        db.add(row)
    else:
        row.value = payload
        if not row.description:
            row.description = description
    db.commit()


def _audit_key(date_yyyy_mm_dd: str) -> str:
    return f"bi.audit.{date_yyyy_mm_dd}"


def log_bi_access(
    db: Session,
    *,
    organization_id: Optional[str],
    current_user: User,
    entity_type: str,
    entity_id: str,
    action: str,
    ip_address: Optional[str],
    user_agent: Optional[str],
    before_state: Optional[dict[str, Any]] = None,
    after_state: Optional[dict[str, Any]] = None,
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    key = _audit_key(now.date().isoformat())
    items = _get_json(db, key, organization_id, default=[])

    row = {
        "id": str(uuid.uuid4()),
        "timestamp": now.isoformat(),
        "user_id": current_user.id,
        "user_name": current_user.full_name,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "action": action,
        "ip_address": ip_address,
        "user_agent": user_agent,
        "before_state": before_state,
        "after_state": after_state,
        "extra": extra or {},
    }
    items.append(row)
    _set_json(db, key, organization_id, items[-3000:], description="BI governance access audit log")
    return row


def get_access_history(
    db: Session,
    *,
    organization_id: Optional[str],
    days: int = 30,
    user_id: Optional[str] = None,
    entity_type: Optional[str] = None,
    action: Optional[str] = None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    today = datetime.now(timezone.utc).date()

    for delta in range(max(1, min(days, 90))):
        key = _audit_key((today - timedelta(days=delta)).isoformat())
        out.extend(_get_json(db, key, organization_id, default=[]))

    def keep(item: dict[str, Any]) -> bool:
        if user_id and item.get("user_id") != user_id:
            return False
        if entity_type and item.get("entity_type") != entity_type:
            return False
        if action and item.get("action") != action:
            return False
        return True

    out = [x for x in out if keep(x)]
    out.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return out


def list_lineage(db: Session, *, organization_id: Optional[str], target_table: Optional[str] = None) -> list[dict[str, Any]]:
    rows = _get_json(db, LINEAGE_KEY, organization_id, default=[])
    if target_table:
        rows = [r for r in rows if r.get("target_table") == target_table]
    rows.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return rows


def track_data_lineage(
    db: Session,
    *,
    organization_id: Optional[str],
    current_user: User,
    source_table: str,
    target_table: str,
    transformation_sql: str,
) -> dict[str, Any]:
    rows = _get_json(db, LINEAGE_KEY, organization_id, default=[])
    existing = next(
        (r for r in rows if r.get("source_table") == source_table and r.get("target_table") == target_table),
        None,
    )
    now = _iso_now()
    if existing:
        existing["transformation_sql"] = transformation_sql
        existing["updated_at"] = now
        item = existing
    else:
        item = {
            "id": str(uuid.uuid4()),
            "source_table": source_table,
            "target_table": target_table,
            "transformation_sql": transformation_sql,
            "created_by": current_user.id,
            "created_at": now,
            "updated_at": now,
        }
        rows.append(item)

    _set_json(db, LINEAGE_KEY, organization_id, rows, description="BI governance data lineage")
    return item


def list_field_sensitivity(
    db: Session,
    *,
    organization_id: Optional[str],
    dataset_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    rows = _get_json(db, FIELD_SENSITIVITY_KEY, organization_id, default=[])
    if dataset_id:
        rows = [r for r in rows if r.get("dataset_id") == dataset_id]
    rows.sort(key=lambda x: (x.get("dataset_id", ""), x.get("field_name", "")))
    return rows


def upsert_field_sensitivity(
    db: Session,
    *,
    organization_id: Optional[str],
    dataset_id: str,
    field_name: str,
    sensitivity_level: str,
    pii_fields: list[str],
    requires_approval: bool,
    current_user: User,
) -> dict[str, Any]:
    levels = {"public", "internal", "confidential", "restricted"}
    if sensitivity_level not in levels:
        raise ValueError("invalid_sensitivity_level")

    rows = _get_json(db, FIELD_SENSITIVITY_KEY, organization_id, default=[])
    now = _iso_now()
    existing = next(
        (r for r in rows if r.get("dataset_id") == dataset_id and r.get("field_name") == field_name),
        None,
    )

    if existing:
        existing.update(
            {
                "sensitivity_level": sensitivity_level,
                "pii_fields": pii_fields,
                "requires_approval": bool(requires_approval),
                "updated_at": now,
                "updated_by": current_user.id,
            }
        )
        item = existing
    else:
        item = {
            "id": str(uuid.uuid4()),
            "dataset_id": dataset_id,
            "field_name": field_name,
            "sensitivity_level": sensitivity_level,
            "pii_fields": pii_fields,
            "requires_approval": bool(requires_approval),
            "created_at": now,
            "updated_at": now,
            "created_by": current_user.id,
            "updated_by": current_user.id,
        }
        rows.append(item)

    _set_json(db, FIELD_SENSITIVITY_KEY, organization_id, rows, description="BI governance field sensitivity")
    return item
