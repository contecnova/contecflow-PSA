"""Append-only audit log with chained integrity hash (per-org).

Each row hashes: prev_hash + payload_canonical_json.
A tampered row breaks the chain — verifiable by the eDiscovery exporter.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _canonical(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def write(
    db: Session,
    *,
    organization_id: str,
    actor_user_id: Optional[str],
    actor_client_id: Optional[str],
    action: str,
    entity_type: str,
    entity_id: Optional[str],
    payload: Optional[dict] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
):
    from app.models.collaboration import CollaborationAuditEvent

    payload = payload or {}
    # Find previous event by ordering on created_at desc + id desc for stable tie-break.
    prev = (
        db.query(CollaborationAuditEvent)
        .filter(CollaborationAuditEvent.organization_id == organization_id)
        .order_by(CollaborationAuditEvent.created_at.desc(), CollaborationAuditEvent.id.desc())
        .first()
    )
    prev_hash = prev.integrity_hash if prev and prev.integrity_hash else "GENESIS"
    canonical = f"{prev_hash}|{action}|{entity_type}|{entity_id or ''}|{_canonical(payload)}"
    new_hash = hashlib.sha256(canonical.encode()).hexdigest()

    row = CollaborationAuditEvent(
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        actor_client_id=actor_client_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload,
        ip_address=ip_address,
        user_agent=user_agent,
        integrity_hash=new_hash,
        prev_event_id=prev.id if prev else None,
    )
    db.add(row)
    # Caller is expected to commit as part of their transaction.
    return row


def verify_chain(db: Session, organization_id: str) -> dict:
    """Recompute the chain by following prev_event_id pointers."""
    from app.models.collaboration import CollaborationAuditEvent

    rows = {
        r.id: r
        for r in db.query(CollaborationAuditEvent)
        .filter(CollaborationAuditEvent.organization_id == organization_id)
        .all()
    }
    breaks = []
    # Find the genesis (no prev_event_id) — should be exactly one if data is intact.
    seen_chains = 0
    for start in [r for r in rows.values() if not r.prev_event_id]:
        seen_chains += 1
        prev_hash = "GENESIS"
        cur = start
        visited = set()
        while cur and cur.id not in visited:
            visited.add(cur.id)
            canonical = f"{prev_hash}|{cur.action}|{cur.entity_type}|{cur.entity_id or ''}|{_canonical(cur.payload or {})}"
            h = hashlib.sha256(canonical.encode()).hexdigest()
            if h != cur.integrity_hash:
                breaks.append({"id": cur.id, "expected": h, "got": cur.integrity_hash})
            prev_hash = cur.integrity_hash or h
            # Find children
            children = [r for r in rows.values() if r.prev_event_id == cur.id]
            cur = children[0] if children else None
    return {"total": len(rows), "chains": seen_chains, "breaks": breaks, "is_valid": not breaks}


# Public alias
audit_log = type("AuditLog", (), {"write": staticmethod(write), "verify_chain": staticmethod(verify_chain)})
