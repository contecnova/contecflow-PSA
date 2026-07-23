"""
CMDB Models & Reconciliation Logic — Data matching and transformation
=========================================================================
Funciones de matching, deduplicación, reportes de drift y gestión de agentes.
"""
import hashlib
import logging
import secrets
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.cmdb import CMDBChangelog, CMDBItem
from app.services.cmdb.parser import compute_config_hash, string_similarity
from app.services.cmdb.utils import utcnow, PROVIDER_AGENT

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# CHANGELOG & AUDIT
# ═══════════════════════════════════════════════════════════════════════════════

def write_changelog(
    db: Session,
    item: CMDBItem,
    action: str,
    field: str | None,
    old_value: str | None,
    new_value: str | None,
    summary: str,
) -> None:
    """Append a CMDBChangelog record for a CI change detected during discovery."""
    entry = CMDBChangelog(
        id=str(uuid4()),
        item_id=item.id,
        user_id=None,  # system/scheduler — no human user
        action=action,
        field=field,
        old_value=(old_value[:4000] if old_value else None),
        new_value=(new_value[:4000] if new_value else None),
        summary=summary[:500],
    )
    db.add(entry)


# ═══════════════════════════════════════════════════════════════════════════════
# RECONCILIATION (Core matching and sync logic)
# ═══════════════════════════════════════════════════════════════════════════════

def reconcile_cis(
    db: Session,
    discovered_cis: list[dict],
    provider_type: str,
) -> dict[str, int]:
    """Compara CIs descubiertos con los existentes en la BD y aplica cambios.

    Estrategia de matching: external_id + discovery_provider (únicos juntos).
    - Si no existe → CREATE.
    - Si existe y hay cambios → UPDATE (name, status, ip, hostname, version, attributes).
    - CIs que pertenecen al proveedor pero no aparecen en el scan → deactivate (status="decommissioned").

    Returns:
        dict con contadores: {"created": N, "updated": N, "deactivated": N}
    """
    created = updated = deactivated = 0
    now = utcnow()

    discovered_ext_ids = {ci["external_id"] for ci in discovered_cis}

    for ci_data in discovered_cis:
        ext_id = ci_data["external_id"]
        existing: CMDBItem | None = (
            db.query(CMDBItem)
            .filter(
                CMDBItem.external_id == ext_id,
                CMDBItem.discovery_provider == provider_type,
            )
            .first()
        )

        if existing is None:
            # CREATE
            new_ci = CMDBItem(
                id=str(uuid4()),
                name=ci_data.get("name", ext_id),
                ci_type=ci_data.get("ci_type", "server"),
                status=ci_data.get("status", "active"),
                environment=ci_data.get("environment", "production"),
                ip_address=ci_data.get("ip_address"),
                hostname=ci_data.get("hostname"),
                version=ci_data.get("version"),
                description=ci_data.get("description"),
                attributes=ci_data.get("attributes"),
                external_id=ext_id,
                discovery_provider=provider_type,
                is_discovered=True,
                last_discovered_at=now,
                config_hash=compute_config_hash(ci_data.get("attributes")),
            )
            db.add(new_ci)
            write_changelog(
                db, new_ci, "created", None, None,
                ci_data.get("name", ext_id),
                f"[discovery:{provider_type}] CI creado automáticamente",
            )
            created += 1
        else:
            # UPDATE if any field changed; detect attribute/config drift separately
            changed = False
            for field in ("name", "status", "ip_address", "hostname", "version",
                          "description", "attributes", "environment"):
                new_val = ci_data.get(field)
                if new_val is not None and getattr(existing, field) != new_val:
                    write_changelog(
                        db, existing, "updated", field,
                        str(getattr(existing, field, "")),
                        str(new_val),
                        f"[discovery:{provider_type}] Campo '{field}' actualizado",
                    )
                    setattr(existing, field, new_val)
                    changed = True

            # Drift detection: compare config hash of attributes
            new_hash = compute_config_hash(ci_data.get("attributes"))
            if new_hash and existing.config_hash and new_hash != existing.config_hash:
                existing.drift_detected_at = now
                logger.info(
                    "Drift detectado en CI %s (%s): hash %s → %s",
                    existing.id, existing.name, existing.config_hash, new_hash,
                )
            existing.config_hash = new_hash
            existing.last_discovered_at = now
            existing.is_discovered = True
            if changed:
                updated += 1

    # Deactivate stale CIs (visible to this provider but not seen in current scan)
    stale = (
        db.query(CMDBItem)
        .filter(
            CMDBItem.discovery_provider == provider_type,
            CMDBItem.is_discovered.is_(True),
            CMDBItem.status != "decommissioned",
        )
        .all()
    )
    for ci in stale:
        if ci.external_id not in discovered_ext_ids:
            write_changelog(
                db, ci, "updated", "status",
                ci.status, "decommissioned",
                f"[discovery:{provider_type}] CI no encontrado en scan — marcado como decommissioned",
            )
            ci.status = "decommissioned"
            deactivated += 1

    db.flush()
    logger.info(
        "Reconcile [%s]: created=%d, updated=%d, deactivated=%d",
        provider_type,
        created,
        updated,
        deactivated,
    )
    return {"created": created, "updated": updated, "deactivated": deactivated}


# ═══════════════════════════════════════════════════════════════════════════════
# ANALYTICS & REPORTING
# ═══════════════════════════════════════════════════════════════════════════════

def get_drift_report(db: Session, hours: int = 24) -> dict:
    """Return CIs where config drift was detected in the last `hours` hours.

    For each drifted CI, include the most recent changelog entries for that CI.

    Returns a dict suitable for the REST drift-report endpoint.
    """
    cutoff = utcnow() - timedelta(hours=max(1, hours))

    drifted = (
        db.query(CMDBItem)
        .filter(
            CMDBItem.drift_detected_at >= cutoff,
            CMDBItem.is_discovered.is_(True),
        )
        .order_by(CMDBItem.drift_detected_at.desc())
        .all()
    )

    items = []
    for ci in drifted:
        # Get the 5 most recent changelog entries for this CI
        changelog_rows = (
            db.query(CMDBChangelog)
            .filter(CMDBChangelog.item_id == ci.id)
            .order_by(CMDBChangelog.created_at.desc())
            .limit(5)
            .all()
        )
        changelog = [
            {
                "field": row.field,
                "old_value": row.old_value,
                "new_value": row.new_value,
                "summary": row.summary,
                "created_at": row.created_at,
            }
            for row in changelog_rows
        ]
        items.append(
            {
                "ci_id": ci.id,
                "name": ci.name,
                "ci_type": ci.ci_type,
                "environment": ci.environment,
                "provider": ci.discovery_provider,
                "drift_detected_at": ci.drift_detected_at,
                "last_discovered_at": ci.last_discovered_at,
                "ip_address": ci.ip_address,
                "hostname": ci.hostname,
                "recent_changelog": changelog,
            }
        )

    return {
        "hours": hours,
        "cutoff": cutoff,
        "total_drifted": len(items),
        "items": items,
    }


def get_reconciliation_health(db: Session, provider_type: str | None = None) -> dict:
    """Build reconciliation health metrics for discovered CIs.

    Metrics:
      - total_discovered: discovered CIs in CMDB
      - active_discovered: discovered CIs currently active/maintenance
      - stale_discovered: discovered CIs decommissioned by reconciliation
      - duplicate_external_ids: repeated (provider, external_id) pairs
      - by_provider: per-provider counts
    """
    q = db.query(CMDBItem).filter(CMDBItem.is_discovered.is_(True))
    if provider_type:
        q = q.filter(CMDBItem.discovery_provider == provider_type)

    rows = q.all()
    total_discovered = len(rows)
    stale_discovered = sum(1 for r in rows if r.status == "decommissioned")
    active_discovered = total_discovered - stale_discovered

    dup_q = (
        db.query(
            CMDBItem.discovery_provider,
            CMDBItem.external_id,
            func.count(CMDBItem.id).label("n"),
        )
        .filter(CMDBItem.is_discovered.is_(True), CMDBItem.external_id.isnot(None))
        .group_by(CMDBItem.discovery_provider, CMDBItem.external_id)
        .having(func.count(CMDBItem.id) > 1)
    )
    if provider_type:
        dup_q = dup_q.filter(CMDBItem.discovery_provider == provider_type)

    duplicate_external_ids = dup_q.count()

    provider_counts = {}
    for r in rows:
        key = r.discovery_provider or "unknown"
        if key not in provider_counts:
            provider_counts[key] = {
                "total": 0,
                "active": 0,
                "decommissioned": 0,
            }
        provider_counts[key]["total"] += 1
        if r.status == "decommissioned":
            provider_counts[key]["decommissioned"] += 1
        else:
            provider_counts[key]["active"] += 1

    score = 100
    if total_discovered > 0:
        stale_ratio = stale_discovered / total_discovered
        score -= int(stale_ratio * 35)
    score -= min(duplicate_external_ids * 10, 35)
    score = max(score, 0)

    return {
        "provider_filter": provider_type,
        "total_discovered": total_discovered,
        "active_discovered": active_discovered,
        "stale_discovered": stale_discovered,
        "duplicate_external_ids": duplicate_external_ids,
        "reconciliation_score": score,
        "by_provider": provider_counts,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# DEDUPLICATION
# ═══════════════════════════════════════════════════════════════════════════════

def ci_similarity_score(ci_a: CMDBItem, ci_b: CMDBItem) -> float:
    """Similarity score in [0,1] for duplicate candidate detection."""
    name_score = string_similarity(ci_a.name, ci_b.name)
    host_score = string_similarity(ci_a.hostname, ci_b.hostname)
    ip_score = 1.0 if ci_a.ip_address and ci_a.ip_address == ci_b.ip_address else 0.0
    type_score = 1.0 if ci_a.ci_type == ci_b.ci_type else 0.0
    env_score = 1.0 if ci_a.environment == ci_b.environment else 0.0
    return round(name_score * 0.45 + host_score * 0.25 + ip_score * 0.2 + type_score * 0.07 + env_score * 0.03, 4)


def deduplicate_candidates(
    db: Session,
    *,
    provider_type: str | None = None,
    min_confidence: float = 0.85,
) -> list[dict]:
    """Find possible duplicates and return merge candidates with confidence score."""
    q = db.query(CMDBItem).filter(CMDBItem.is_discovered.is_(True), CMDBItem.status != "decommissioned")
    if provider_type:
        q = q.filter(CMDBItem.discovery_provider == provider_type)
    rows = q.order_by(CMDBItem.discovery_provider.asc(), CMDBItem.name.asc()).all()

    candidates: list[dict] = []
    for i in range(len(rows)):
        a = rows[i]
        for j in range(i + 1, len(rows)):
            b = rows[j]
            if provider_type and (a.discovery_provider != b.discovery_provider):
                continue
            score = ci_similarity_score(a, b)
            if score < min_confidence:
                continue
            keeper, duplicate = (a, b)
            if (b.last_discovered_at or datetime.min) > (a.last_discovered_at or datetime.min):
                keeper, duplicate = (b, a)

            candidates.append(
                {
                    "provider": a.discovery_provider or b.discovery_provider,
                    "confidence": score,
                    "keeper": {
                        "id": keeper.id,
                        "name": keeper.name,
                        "hostname": keeper.hostname,
                        "ip_address": keeper.ip_address,
                    },
                    "duplicate": {
                        "id": duplicate.id,
                        "name": duplicate.name,
                        "hostname": duplicate.hostname,
                        "ip_address": duplicate.ip_address,
                    },
                }
            )
    candidates.sort(key=lambda x: x["confidence"], reverse=True)
    return candidates


def auto_merge_duplicates(
    db: Session,
    *,
    provider_type: str | None = None,
    min_confidence: float = 0.85,
    limit: int = 100,
) -> dict:
    """Apply automatic deduplication by decommissioning likely duplicate CIs."""
    candidates = deduplicate_candidates(
        db,
        provider_type=provider_type,
        min_confidence=min_confidence,
    )[: max(1, limit)]

    merged = 0
    applied: list[dict] = []
    for c in candidates:
        dup = db.query(CMDBItem).filter(CMDBItem.id == c["duplicate"]["id"]).first()
        keep = db.query(CMDBItem).filter(CMDBItem.id == c["keeper"]["id"]).first()
        if not dup or not keep or dup.status == "decommissioned":
            continue

        dup.status = "decommissioned"
        note = f"[auto-merge] merged_into={keep.id} confidence={c['confidence']}"
        dup.description = f"{dup.description or ''}\n{note}".strip()
        merged += 1
        applied.append(c)

    db.flush()
    return {
        "provider_filter": provider_type,
        "min_confidence": min_confidence,
        "candidates": len(candidates),
        "merged": merged,
        "applied": applied,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT MANAGEMENT (On-Premise Discovery)
# ═══════════════════════════════════════════════════════════════════════════════

def generate_agent_token(
    db: Session,
    name: str,
    description: str | None = None,
    os_type: str | None = None,
    created_by: str | None = None,
) -> dict:
    """Register a new on-premise agent and return a one-time bearer token.

    The raw token is **never stored**.  Only its SHA-256 hex digest is persisted.
    The caller must deliver the token to the target host; it cannot be recovered later.

    Returns:
        {
            "agent_id": str,
            "token": str,          # raw token — deliver to host, never stored again
            "token_prefix": str,   # first 8 chars shown in UI for identification
            "name": str,
        }
    """
    from app.models.cmdb import CMDBAgentRegistration  # noqa: PLC0415

    raw_token = secrets.token_hex(32)          # 64-char hex = 256-bit entropy
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    token_prefix = raw_token[:8]

    reg = CMDBAgentRegistration(
        id=str(uuid4()),
        name=name,
        description=description,
        token_hash=token_hash,
        token_prefix=token_prefix,
        os_type=os_type,
        is_active=True,
        created_by=created_by,
    )
    db.add(reg)
    db.flush()

    logger.info("Agent registered: %s (id=%s, prefix=%s)", name, reg.id, token_prefix)

    return {
        "agent_id": reg.id,
        "token": raw_token,
        "token_prefix": token_prefix,
        "name": name,
    }


def list_agent_registrations(db: Session) -> list[dict]:
    """Return all agent registrations with last check-in info."""
    from app.models.cmdb import CMDBAgentRegistration  # noqa: PLC0415

    rows = db.query(CMDBAgentRegistration).order_by(CMDBAgentRegistration.created_at.desc()).all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "description": r.description,
            "token_prefix": r.token_prefix,
            "os_type": r.os_type,
            "is_active": r.is_active,
            "last_checkin_at": r.last_checkin_at,
            "last_checkin_ip": r.last_checkin_ip,
            "last_hostname": r.last_hostname,
            "ci_id": r.ci_id,
            "created_at": r.created_at,
        }
        for r in rows
    ]


def revoke_agent_token(db: Session, agent_id: str) -> None:
    """Deactivate an agent registration (revoke its token)."""
    from fastapi import HTTPException  # noqa: PLC0415
    from app.models.cmdb import CMDBAgentRegistration  # noqa: PLC0415

    reg = db.query(CMDBAgentRegistration).filter(CMDBAgentRegistration.id == agent_id).first()
    if not reg:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    reg.is_active = False
    db.flush()


def rotate_agent_token(db: Session, agent_id: str) -> dict:
    """Generate a new token for an agent registration.

    The old token is immediately invalidated.  Returns the new raw token once.
    """
    from fastapi import HTTPException  # noqa: PLC0415
    from app.models.cmdb import CMDBAgentRegistration  # noqa: PLC0415

    reg = db.query(CMDBAgentRegistration).filter(CMDBAgentRegistration.id == agent_id).first()
    if not reg:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    raw_token = secrets.token_hex(32)
    reg.token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    reg.token_prefix = raw_token[:8]
    reg.is_active = True
    db.flush()

    return {
        "agent_id": reg.id,
        "token": raw_token,
        "token_prefix": reg.token_prefix,
        "name": reg.name,
    }


def process_agent_checkin(
    db: Session,
    raw_token: str,
    payload: dict,
    client_ip: str | None = None,
) -> dict:
    """Process an inbound check-in from an on-premise agent.

    1. Validates the bearer token.
    2. Normalizes the payload to a CI dict.
    3. Calls reconcile_cis (upsert) for this single host.
    4. Updates the agent registration (last_checkin_at, hostname, ci_id).

    Returns summary dict with `agent_id`, `ci_id`, `created`/`updated` flags.
    """
    from fastapi import HTTPException  # noqa: PLC0415
    from app.services.cmdb.parser import resolve_agent_by_token, normalize_agent_payload  # noqa: PLC0415

    reg = resolve_agent_by_token(db, raw_token)
    if not reg:
        raise HTTPException(status_code=401, detail="Invalid or revoked agent token")

    ci_dict = normalize_agent_payload(payload, reg.id)

    # Reconcile just this single agent's CI
    stats = reconcile_cis(db, [ci_dict], PROVIDER_AGENT)

    # Find the CI that was created/updated
    ci = (
        db.query(CMDBItem)
        .filter(
            CMDBItem.external_id == ci_dict["external_id"],
            CMDBItem.discovery_provider == PROVIDER_AGENT,
        )
        .first()
    )

    # Update registration metadata
    now = utcnow()
    reg.last_checkin_at = now
    if client_ip:
        reg.last_checkin_ip = client_ip
    reg.last_hostname = ci_dict["name"]
    if ci:
        reg.ci_id = ci.id
    if not reg.os_type and payload.get("os_type"):
        reg.os_type = payload["os_type"].lower()[:10]
    db.flush()

    return {
        "ok": True,
        "agent_id": reg.id,
        "ci_id": ci.id if ci else None,
        "hostname": ci_dict["name"],
        "created": stats["created"],
        "updated": stats["updated"],
        "checkin_at": now.isoformat(),
    }
