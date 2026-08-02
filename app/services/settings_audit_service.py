"""Audit logger for settings + integration-credential changes.

Every write through ``settings_service.set_runtime_value`` and
``integration_credentials_service.set_credential`` calls ``record_change``
here. Secret values are never persisted — only SHA-256 hashes of (old, new)
let an auditor verify after the fact "was this the value at time T?" without
exposing the secret again.

Read access goes through :func:`query_audit_log` and is admin-only at the
endpoint layer.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.settings import SettingsAuditLog

logger = logging.getLogger("contecflow.settings.audit")


def _hash(value: Optional[str]) -> Optional[str]:
    """SHA-256 hex of the stringified value, or None for empty/None."""
    if value is None or value == "":
        return None
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def record_change(
    db: Session,
    *,
    scope: str,                      # "runtime" | "integration"
    key: str,
    is_secret: bool,
    old_value: Optional[Any],
    new_value: Optional[Any],
    actor_id: Optional[str] = None,
    actor_ip: Optional[str] = None,
    actor_ua: Optional[str] = None,
    organization_id: Optional[str] = None,
    provider: Optional[str] = None,
) -> None:
    """Append a row to `settings_audit_log`. Never raises into the caller."""
    try:
        if scope not in ("runtime", "integration"):
            return
        old_s = None if old_value is None else str(old_value)
        new_s = None if new_value is None else str(new_value)
        action = "clear" if new_s in (None, "") else "set"

        entry = SettingsAuditLog(
            scope=scope,
            provider=provider,
            key=key,
            action=action,
            is_secret=bool(is_secret),
            # Plaintext only for non-secret rows. Hashes always.
            old_value=None if is_secret else old_s,
            new_value=None if is_secret else new_s,
            old_value_hash=_hash(old_s) if is_secret else None,
            new_value_hash=_hash(new_s) if is_secret else None,
            actor_id=actor_id,
            actor_ip=(actor_ip[:64] if actor_ip else None),
            actor_ua=(actor_ua[:255] if actor_ua else None),
            organization_id=organization_id,
        )
        db.add(entry)
        db.commit()
    except Exception as exc:
        # Audit must not block business writes — log and swallow.
        try:
            db.rollback()
        except Exception:
            logger.debug("record_change: fallo best-effort ignorado", exc_info=True)
        logger.warning("settings audit log failed (scope=%s key=%s): %s", scope, key, exc)


def query_audit_log(
    db: Session,
    *,
    scope: Optional[str] = None,
    key: Optional[str] = None,
    provider: Optional[str] = None,
    actor_id: Optional[str] = None,
    organization_id: Optional[str] = None,
    since: Optional[datetime] = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[SettingsAuditLog], int]:
    """Return (rows, total). Most-recent first. Caller enforces RBAC."""
    q = db.query(SettingsAuditLog)
    if scope:
        q = q.filter(SettingsAuditLog.scope == scope)
    if key:
        q = q.filter(SettingsAuditLog.key == key)
    if provider:
        q = q.filter(SettingsAuditLog.provider == provider)
    if actor_id:
        q = q.filter(SettingsAuditLog.actor_id == actor_id)
    if organization_id:
        q = q.filter(SettingsAuditLog.organization_id == organization_id)
    if since:
        q = q.filter(SettingsAuditLog.created_at >= since)
    total = q.count()
    rows = (
        q.order_by(SettingsAuditLog.created_at.desc(), SettingsAuditLog.id.desc())
        .offset(max(0, offset))
        .limit(max(1, min(limit, 500)))
        .all()
    )
    return rows, total


def serialize(row: SettingsAuditLog) -> dict:
    return {
        "id": row.id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "scope": row.scope,
        "provider": row.provider,
        "key": row.key,
        "action": row.action,
        "is_secret": bool(row.is_secret),
        "old_value": row.old_value,
        "new_value": row.new_value,
        "old_value_hash": row.old_value_hash,
        "new_value_hash": row.new_value_hash,
        "actor_id": row.actor_id,
        "actor_ip": row.actor_ip,
        "actor_ua": row.actor_ua,
        "organization_id": row.organization_id,
    }


__all__ = ["record_change", "query_audit_log", "serialize"]
