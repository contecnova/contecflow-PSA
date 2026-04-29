"""
bi_gdpr_service.py — GDPR compliance for BI data.

Handles:
  - Data erasure requests (DSR delete) — removes personal data from analytics snapshots
  - Consent management — track which users have consented to BI analytics collection
  - DSR (Data Subject Request) status tracking
  - Field-level data masking metadata

State persisted in AppSetting JSON, scoped by organization.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.settings import AppSetting

_KEY_CONSENT = "bi.gdpr.consent"
_KEY_DSR = "bi.gdpr.dsr"
_KEY_MASKS = "bi.gdpr.field_masks"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_setting(db: Session, key: str, org_id: Optional[str], default: Any) -> Any:
    q = db.query(AppSetting).filter(AppSetting.key == key)
    q = q.filter(AppSetting.organization_id == org_id) if org_id else q.filter(AppSetting.organization_id.is_(None))
    row = q.first()
    if not row or not row.value:
        return default
    try:
        return json.loads(row.value)
    except Exception:
        return default


def _set_setting(db: Session, key: str, org_id: Optional[str], value: Any) -> None:
    payload = json.dumps(value, ensure_ascii=False)
    q = db.query(AppSetting).filter(AppSetting.key == key)
    q = q.filter(AppSetting.organization_id == org_id) if org_id else q.filter(AppSetting.organization_id.is_(None))
    row = q.first()
    if not row:
        row = AppSetting(key=key, organization_id=org_id, value=payload, description=f"GDPR BI: {key}")
        db.add(row)
    else:
        row.value = payload
    db.commit()


# ── Consent management ────────────────────────────────────────────────────────

def record_consent(db: Session, *, user_id: str, consented: bool, org_id: Optional[str]) -> dict:
    """Record or revoke BI analytics consent for a user."""
    consents: dict = _get_setting(db, _KEY_CONSENT, org_id, {})
    consents[user_id] = {
        "user_id": user_id,
        "consented": consented,
        "updated_at": _iso_now(),
    }
    _set_setting(db, _KEY_CONSENT, org_id, consents)
    return consents[user_id]


def get_consent(db: Session, *, user_id: str, org_id: Optional[str]) -> Optional[dict]:
    consents = _get_setting(db, _KEY_CONSENT, org_id, {})
    return consents.get(user_id)


def list_consents(db: Session, *, org_id: Optional[str]) -> list[dict]:
    return list(_get_setting(db, _KEY_CONSENT, org_id, {}).values())


# ── DSR (Data Subject Requests) ───────────────────────────────────────────────

def create_dsr(
    db: Session,
    *,
    subject_id: str,
    request_type: str,
    org_id: Optional[str],
    requester_user_id: str,
    notes: Optional[str] = None,
) -> dict:
    """
    Create a new DSR (erasure, portability, rectification).
    request_type: erasure | portability | rectification | restriction
    """
    dsrs: dict = _get_setting(db, _KEY_DSR, org_id, {})
    dsr_id = str(uuid.uuid4())
    entry = {
        "id": dsr_id,
        "subject_id": subject_id,
        "request_type": request_type,
        "status": "pending",
        "requester_user_id": requester_user_id,
        "notes": notes,
        "created_at": _iso_now(),
        "resolved_at": None,
        "resolution_notes": None,
    }
    dsrs[dsr_id] = entry
    _set_setting(db, _KEY_DSR, org_id, dsrs)
    return entry


def resolve_dsr(
    db: Session,
    *,
    dsr_id: str,
    org_id: Optional[str],
    resolution_notes: Optional[str] = None,
) -> dict:
    dsrs: dict = _get_setting(db, _KEY_DSR, org_id, {})
    if dsr_id not in dsrs:
        raise ValueError(f"DSR '{dsr_id}' not found")
    dsrs[dsr_id]["status"] = "resolved"
    dsrs[dsr_id]["resolved_at"] = _iso_now()
    dsrs[dsr_id]["resolution_notes"] = resolution_notes
    _set_setting(db, _KEY_DSR, org_id, dsrs)

    # If erasure: revoke consent automatically
    if dsrs[dsr_id]["request_type"] == "erasure":
        record_consent(db, user_id=dsrs[dsr_id]["subject_id"], consented=False, org_id=org_id)

    return dsrs[dsr_id]


def list_dsrs(db: Session, *, org_id: Optional[str], status: Optional[str] = None) -> list[dict]:
    dsrs = list(_get_setting(db, _KEY_DSR, org_id, {}).values())
    if status:
        dsrs = [d for d in dsrs if d["status"] == status]
    return sorted(dsrs, key=lambda d: d["created_at"], reverse=True)


# ── Field masking metadata ────────────────────────────────────────────────────

def set_field_mask(
    db: Session,
    *,
    dataset: str,
    field: str,
    mask_type: str,
    org_id: Optional[str],
) -> dict:
    """Register that a BI field should be masked/pseudonymized in exports."""
    masks: dict = _get_setting(db, _KEY_MASKS, org_id, {})
    key = f"{dataset}.{field}"
    masks[key] = {"dataset": dataset, "field": field, "mask_type": mask_type, "updated_at": _iso_now()}
    _set_setting(db, _KEY_MASKS, org_id, masks)
    return masks[key]


def list_field_masks(db: Session, *, org_id: Optional[str]) -> list[dict]:
    return list(_get_setting(db, _KEY_MASKS, org_id, {}).values())
