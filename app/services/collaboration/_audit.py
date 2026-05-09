"""Append-only audit log with chained integrity hash (per-org).

Each row hashes: prev_hash + payload_canonical_json.
A tampered row breaks the chain — verifiable by the eDiscovery exporter.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _canonical(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


# In-process per-org lock para que dos requests concurrentes no obtengan el
# mismo `prev` y rompan la cadena. Para multi-worker en prod se debe usar un
# advisory lock en DB (Postgres `pg_advisory_xact_lock`) o serializable.
_org_locks: dict[str, threading.Lock] = {}
_locks_meta_lock = threading.Lock()


def _lock_for(org_id: str) -> threading.Lock:
    lk = _org_locks.get(org_id)
    if lk is None:
        with _locks_meta_lock:
            lk = _org_locks.get(org_id) or threading.Lock()
            _org_locks[org_id] = lk
    return lk


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
    # Per-org lock: garantiza que dos requests concurrentes no calculen el
    # mismo prev_hash y rompan la cadena. Si el backend es Postgres se podría
    # usar `with_for_update()` en lugar de un lock en proceso.
    with _lock_for(organization_id):
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
        # Caller hace commit en su transacción (mantenemos el lock hasta el
        # return; si el caller quiere propagar fuera del lock, puede; el lock
        # solo evita que otra escritura `audit.write` empiece a calcular prev).
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
