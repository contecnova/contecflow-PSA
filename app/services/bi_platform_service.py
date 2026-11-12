"""BI Platform service orchestration.

Platform-scale capabilities:
- Embedded analytics SDK settings + token payload support
- 20+ connector catalog and custom connector framework
- Data lineage + access audit metadata
- Dataset versioning snapshots + diffs

State is persisted in AppSetting JSON by organization.
"""
from __future__ import annotations
import logging

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.settings import AppSetting
from app.models.user import User

LINEAGE_KEY = "bi.phase3.governance.lineage"
FIELD_SENSITIVITY_KEY = "bi.phase3.governance.field_sensitivity"

SENSITIVITY_LEVELS = {"public", "internal", "confidential", "restricted"}


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
        logging.getLogger(__name__).debug("_get_json: excepcion ignorada", exc_info=True)
        return default


def _set_json(db: Session, key: str, organization_id: Optional[str], value: Any, description: str) -> None:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    row = _setting_row(db, key, organization_id)
    if not row:
        row = AppSetting(
            key=key,
            organization_id=organization_id,
            description=description,
            value=payload,
        )
        db.add(row)
    else:
        row.value = payload
        if not row.description:
            row.description = description
    db.commit()
















def _default_lineage_state() -> dict[str, Any]:
    return {"edges": [], "audit": []}


def get_lineage(db: Session, *, organization_id: Optional[str]) -> dict[str, Any]:
    return _get_json(db, LINEAGE_KEY, organization_id, default=_default_lineage_state())


def upsert_lineage_edge(
    db: Session,
    *,
    organization_id: Optional[str],
    source_table: str,
    target_table: str,
    transformation_sql: str,
    current_user: User,
) -> dict[str, Any]:
    state = get_lineage(db, organization_id=organization_id)
    edges = state.get("edges", [])
    existing = None
    for e in edges:
        if e.get("source_table") == source_table and e.get("target_table") == target_table:
            existing = e
            break

    now = _iso_now()
    if existing:
        existing["transformation_sql"] = transformation_sql
        existing["updated_at"] = now
        row = existing
    else:
        row = {
            "id": str(uuid.uuid4()),
            "source_table": source_table,
            "target_table": target_table,
            "transformation_sql": transformation_sql,
            "created_by": current_user.id,
            "created_at": now,
            "updated_at": now,
        }
        edges.append(row)

    state["edges"] = edges
    _set_json(
        db,
        LINEAGE_KEY,
        organization_id,
        state,
        description="BI Platform governance lineage and audit (JSON)",
    )
    return row


def log_access_event(
    db: Session,
    *,
    organization_id: Optional[str],
    current_user: User,
    entity_type: str,
    entity_id: str,
    action: str,
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    state = get_lineage(db, organization_id=organization_id)
    audit = state.get("audit", [])
    row = {
        "id": str(uuid.uuid4()),
        "timestamp": _iso_now(),
        "user_id": current_user.id,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "action": action,
        "extra": extra or {},
    }
    audit.append(row)
    # Keep bounded audit footprint.
    state["audit"] = audit[-2000:]
    _set_json(
        db,
        LINEAGE_KEY,
        organization_id,
        state,
        description="BI Platform governance lineage and audit (JSON)",
    )
    return row


def _version_key(dataset_key: str) -> str:
    return f"bi.phase3.versioning.{dataset_key}"


def list_dataset_snapshots(db: Session, *, organization_id: Optional[str], dataset_key: str) -> list[dict[str, Any]]:
    return _get_json(db, _version_key(dataset_key), organization_id, default=[])


def create_dataset_snapshot(
    db: Session,
    *,
    organization_id: Optional[str],
    dataset_key: str,
    payload: dict[str, Any],
    current_user: User,
) -> dict[str, Any]:
    snapshots = list_dataset_snapshots(db, organization_id=organization_id, dataset_key=dataset_key)
    row = {
        "id": str(uuid.uuid4()),
        "dataset_key": dataset_key,
        "created_at": _iso_now(),
        "created_by": current_user.id,
        "payload": payload,
    }
    snapshots.append(row)
    snapshots = snapshots[-100:]
    _set_json(
        db,
        _version_key(dataset_key),
        organization_id,
        snapshots,
        description=f"BI Platform dataset versioning snapshots for {dataset_key}",
    )
    return row


def diff_snapshots(
    db: Session,
    *,
    organization_id: Optional[str],
    dataset_key: str,
    from_id: str,
    to_id: str,
) -> dict[str, Any]:
    snapshots = list_dataset_snapshots(db, organization_id=organization_id, dataset_key=dataset_key)
    from_snap = next((x for x in snapshots if x.get("id") == from_id), None)
    to_snap = next((x for x in snapshots if x.get("id") == to_id), None)
    if not from_snap or not to_snap:
        raise ValueError("snapshot_not_found")

    a = from_snap.get("payload") or {}
    b = to_snap.get("payload") or {}
    keys = sorted(set(a.keys()) | set(b.keys()))

    changes = []
    for key in keys:
        if a.get(key) != b.get(key):
            changes.append({
                "field": key,
                "from": a.get(key),
                "to": b.get(key),
            })

    return {
        "dataset_key": dataset_key,
        "from_id": from_id,
        "to_id": to_id,
        "changes": changes,
        "change_count": len(changes),
    }


# ── Field-level sensitivity classification ────────────────────────────────────

def list_field_sensitivity(
    db: Session,
    *,
    organization_id: Optional[str],
    dataset_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    items = _get_json(db, FIELD_SENSITIVITY_KEY, organization_id, default=[])
    if dataset_id:
        items = [i for i in items if i.get("dataset_id") == dataset_id]
    return items


def upsert_field_sensitivity(
    db: Session,
    *,
    organization_id: Optional[str],
    dataset_id: str,
    field_name: str,
    sensitivity_level: str,
    pii_types: Optional[list[str]],
    requires_approval: bool,
    current_user: User,
) -> dict[str, Any]:
    if sensitivity_level not in SENSITIVITY_LEVELS:
        raise ValueError("invalid_sensitivity_level")

    items = list_field_sensitivity(db, organization_id=organization_id)
    existing = next(
        (i for i in items if i.get("dataset_id") == dataset_id and i.get("field_name") == field_name),
        None,
    )
    now = _iso_now()
    if existing:
        existing["sensitivity_level"] = sensitivity_level
        existing["pii_types"] = pii_types or []
        existing["requires_approval"] = requires_approval
        existing["updated_by"] = current_user.id
        existing["updated_at"] = now
        row = existing
    else:
        row = {
            "id": str(uuid.uuid4()),
            "dataset_id": dataset_id,
            "field_name": field_name,
            "sensitivity_level": sensitivity_level,
            "pii_types": pii_types or [],
            "requires_approval": requires_approval,
            "created_by": current_user.id,
            "created_at": now,
            "updated_by": current_user.id,
            "updated_at": now,
        }
        items.append(row)

    _set_json(
        db,
        FIELD_SENSITIVITY_KEY,
        organization_id,
        items,
        description="BI Platform field-level sensitivity classification (JSON)",
    )
    return row


def delete_field_sensitivity(
    db: Session,
    *,
    organization_id: Optional[str],
    sensitivity_id: str,
) -> bool:
    items = list_field_sensitivity(db, organization_id=organization_id)
    new_items = [i for i in items if i.get("id") != sensitivity_id]
    if len(new_items) == len(items):
        return False
    _set_json(
        db,
        FIELD_SENSITIVITY_KEY,
        organization_id,
        new_items,
        description="BI Platform field-level sensitivity classification (JSON)",
    )
    return True


def get_sensitivity_summary(
    db: Session,
    *,
    organization_id: Optional[str],
) -> dict[str, Any]:
    """Return count of fields per sensitivity level and datasets with restricted/PII fields."""
    items = list_field_sensitivity(db, organization_id=organization_id)
    by_level: dict[str, int] = {lvl: 0 for lvl in SENSITIVITY_LEVELS}
    pii_datasets: set[str] = set()
    restricted_datasets: set[str] = set()
    for item in items:
        lvl = item.get("sensitivity_level", "public")
        by_level[lvl] = by_level.get(lvl, 0) + 1
        if item.get("pii_types"):
            pii_datasets.add(item.get("dataset_id", ""))
        if lvl == "restricted":
            restricted_datasets.add(item.get("dataset_id", ""))
    return {
        "total_classified_fields": len(items),
        "by_level": by_level,
        "datasets_with_pii": sorted(pii_datasets),
        "datasets_with_restricted_fields": sorted(restricted_datasets),
    }
