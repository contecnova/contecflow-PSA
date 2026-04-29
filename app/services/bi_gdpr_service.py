"""
bi_gdpr_service.py — GDPR compliance for BI data.

Handles:
  - Data erasure requests (DSR delete) — anonymises personal data in DB + analytics snapshots
  - Consent management — track which users have consented to BI analytics collection
  - DSR (Data Subject Request) status tracking
  - Field-level data masking metadata

State persisted in AppSetting JSON, scoped by organization.
Erasure operations act on real DB rows (Ticket.requester_*, User fields).
"""
from __future__ import annotations

import hashlib
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


# ── Erasure pipeline ──────────────────────────────────────────────────────────

def _anon_hash(value: str) -> str:
    """One-way pseudonymisation: SHA-256 first 12 chars, prefixed."""
    return "[erased:" + hashlib.sha256(value.encode()).hexdigest()[:12] + "]"


def execute_erasure(db: Session, *, subject_id: str, org_id: Optional[str]) -> dict:
    """
    Physically anonymise personal data for *subject_id* across all relevant tables.

    subject_id can be:
      - A User.id — anonymises User row + Ticket requester fields
      - An email string — resolves to User first, then anonymises

    Returns a report of operations performed.
    """
    from app.models.user import User
    from app.models.service_desk import Ticket

    report: dict[str, Any] = {
        "subject_id": subject_id,
        "executed_at": _iso_now(),
        "operations": [],
    }

    # ── Resolve user ──────────────────────────────────────────────────────────
    user_q = db.query(User)
    if "@" in subject_id:
        user = user_q.filter(User.email == subject_id).first()
    else:
        user = user_q.filter(User.id == subject_id).first()

    user_id_for_tickets = subject_id

    if user:
        user_id_for_tickets = user.id
        original_email = user.email
        # Anonymise User row
        user.email = _anon_hash(original_email) + "@erased.invalid"
        user.username = _anon_hash(user.username)
        user.full_name = "[ERASED]"
        user.first_name = "[ERASED]"
        user.last_name = "[ERASED]"
        user.phone = None
        user.avatar_url = None
        db.add(user)
        report["operations"].append({
            "table": "users",
            "row_id": user.id,
            "fields_cleared": ["email", "username", "full_name", "first_name", "last_name", "phone", "avatar_url"],
        })

    # ── Anonymise ticket requester fields ─────────────────────────────────────
    tickets = db.query(Ticket).filter(
        (Ticket.requester_user_id == user_id_for_tickets) |
        (Ticket.requester_email == subject_id)
    ).all()

    for t in tickets:
        if t.requester_name:
            t.requester_name = "[ERASED]"
        if t.requester_email:
            t.requester_email = _anon_hash(t.requester_email) + "@erased.invalid"
        t.requester_user_id = None
        db.add(t)

    if tickets:
        report["operations"].append({
            "table": "sd_tickets",
            "count": len(tickets),
            "fields_cleared": ["requester_name", "requester_email", "requester_user_id"],
        })

    # ── Purge analytics consent & DSR snapshot (no historical PII) ───────────
    consents: dict = _get_setting(db, _KEY_CONSENT, org_id, {})
    if subject_id in consents:
        del consents[subject_id]
        _set_setting(db, _KEY_CONSENT, org_id, consents)
        report["operations"].append({"table": "appsetting[bi.gdpr.consent]", "action": "deleted", "key": subject_id})

    db.commit()
    return report
