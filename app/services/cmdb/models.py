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

from app.models.cmdb import CMDBChangelog
from app.models.service_desk import CIStatus, CIType, ConfigurationItem
from app.services.cmdb.parser import compute_config_hash, string_similarity
from app.services.cmdb.utils import utcnow, PROVIDER_AGENT
from app.core.errores import ErrorDeDominio

#: Lo que el descubrimiento dice del estado, en el estado de la CMDB.
ESTADO_DESCUBIERTO = {
    "active": CIStatus.operational,
    "maintenance": CIStatus.maintenance,
    "decommissioned": CIStatus.retired,
}
_RETIRADO = CIStatus.retired


def _tipo(valor: str | None) -> CIType:
    try:
        return CIType((valor or "other").lower())
    except ValueError:
        return CIType.other


def _estado(valor) -> CIStatus:
    if isinstance(valor, CIStatus):
        return valor
    return ESTADO_DESCUBIERTO.get((valor or "active").lower(), CIStatus.operational)


def _de_la_organizacion(q, org_id: str | None):
    """Acota a una organizacion; `None` es el superadministrador: todo."""
    if org_id is None:
        return q
    return q.filter(ConfigurationItem.organization_id == org_id)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# CHANGELOG & AUDIT
# ═══════════════════════════════════════════════════════════════════════════════

def write_changelog(
    db: Session,
    item: ConfigurationItem,
    action: str,
    field: str | None,
    old_value: str | None,
    new_value: str | None,
    summary: str,
) -> None:
    """Append a CMDBChangelog record for a CI change detected during discovery."""
    entry = CMDBChangelog(
        id=str(uuid4()),
        organization_id=item.organization_id,
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
    *,
    provider=None,
    organization_id: str | None = None,
    retirar_ausentes: bool = True,
) -> dict[str, int]:
    """Compara los CIs descubiertos con la CMDB y aplica los cambios.

    Se casa por `external_id` dentro del proveedor: el concreto si se pasa
    `provider` (dos proveedores AWS ya no se pisan) y, si no, el tipo.

    - No existe -> se crea, con codigo y en la organizacion del proveedor.
    - Existe y cambia -> se actualiza y queda en el historial; si cambia el
      hash de `attributes`, se marca la deriva.
    - Del mismo proveedor y no aparece -> se retira, salvo con
      `retirar_ausentes=False`.

    Auditoria 2026-11: escribia en `cmdb_items`, una CMDB que los tickets no
    veian, y sin organizacion. Y el check-in de un agente pasaba un solo host
    con el tipo `agent`: retiraba los CIs de **todos los demas agentes**. El
    check-in llama ahora con `retirar_ausentes=False`.
    """
    from app.services.sla_service import next_ci_number

    created = updated = deactivated = 0
    now = utcnow()
    org_id = organization_id if organization_id is not None else getattr(provider, "organization_id", None)

    def _del_proveedor(q):
        q = q.filter(ConfigurationItem.discovery_provider == provider_type)
        if provider is not None:
            q = q.filter(ConfigurationItem.discovery_provider_id == provider.id)
        return q.filter(ConfigurationItem.organization_id == org_id) if org_id else q

    discovered_ext_ids = {ci["external_id"] for ci in discovered_cis}

    for ci_data in discovered_cis:
        ext_id = ci_data["external_id"]
        existing: ConfigurationItem | None = _del_proveedor(
            db.query(ConfigurationItem).filter(ConfigurationItem.external_id == ext_id)).first()

        if existing is None:
            new_ci = ConfigurationItem(
                id=str(uuid4()),
                organization_id=org_id,
                code=next_ci_number(db),
                name=ci_data.get("name", ext_id),
                ci_type=_tipo(ci_data.get("ci_type", "server")),
                status=_estado(ci_data.get("status")),
                environment=ci_data.get("environment", "production"),
                ip_address=ci_data.get("ip_address"),
                hostname=ci_data.get("hostname"),
                version=ci_data.get("version"),
                description=ci_data.get("description"),
                attributes=ci_data.get("attributes"),
                external_id=ext_id,
                discovery_provider=provider_type,
                discovery_provider_id=getattr(provider, "id", None),
                is_discovered=True,
                last_discovered_at=now,
                config_hash=compute_config_hash(ci_data.get("attributes")),
            )
            db.add(new_ci)
            db.flush()  # el siguiente codigo tiene que ver este
            write_changelog(
                db, new_ci, "created", None, None,
                ci_data.get("name", ext_id),
                f"[discovery:{provider_type}] CI creado automáticamente",
            )
            created += 1
        else:
            changed = False
            for field in ("name", "status", "ip_address", "hostname", "version",
                          "description", "attributes", "environment"):
                new_val = ci_data.get(field)
                if new_val is None:
                    continue
                if field == "status":
                    new_val = _estado(new_val)
                if getattr(existing, field) != new_val:
                    antes = getattr(existing, field, "")
                    write_changelog(
                        db, existing, "updated", field,
                        str(getattr(antes, "value", antes)),
                        str(getattr(new_val, "value", new_val)),
                        f"[discovery:{provider_type}] Campo '{field}' actualizado",
                    )
                    setattr(existing, field, new_val)
                    changed = True

            # Deriva: cambia el hash de los atributos.
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
            if provider is not None:
                existing.discovery_provider_id = provider.id
            if changed:
                updated += 1

    if retirar_ausentes:
        stale = _del_proveedor(db.query(ConfigurationItem)).filter(
            ConfigurationItem.is_discovered.is_(True),
            ConfigurationItem.status != _RETIRADO,
        ).all()
        for ci in stale:
            if ci.external_id not in discovered_ext_ids:
                write_changelog(
                    db, ci, "updated", "status",
                    str(getattr(ci.status, "value", ci.status)), _RETIRADO.value,
                    f"[discovery:{provider_type}] CI no encontrado en scan — retirado",
                )
                ci.status = _RETIRADO
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

def aprobar_linea_base(
    db: Session,
    current_user,
    provider_id: str,
    ci_id: str | None = None,
) -> dict:
    """Congela `attributes` como linea base aprobada y limpia la deriva.

    Auditoria 2026-08 (hallazgo 22). **Este endpoint no podia aprobar nada.**
    La consulta era:

        db.query(CMDBItem).filter(CMDBItem.discovery_provider == provider_id)

    ...y `CMDBItem.discovery_provider` guarda el **tipo** de proveedor —`aws`,
    `kubernetes`, `vsphere`; asi lo escribe la reconciliacion, con las
    constantes de `services/cmdb/utils.py`—, mientras `provider_id` es el UUID
    de una fila de `cmdb_discovery_providers`. Un UUID nunca es igual a `aws`,
    asi que la consulta devolvia cero filas **siempre** y la respuesta era
    invariablemente `{"ok": false, "error": "No CIs found..."}`. Medido:

        id del proveedor      1add5ac0-82a0-4d6c-812c-e2e1e46794a6
        provider_type         aws
        CI.discovery_provider aws

        consulta del endpoint (por id) ->  0 CIs
        consulta por provider_type     ->  1 CI

    Un endpoint que no puede funcionar nunca es la misma clase de defecto que
    el nodo «crear ticket» de los flujos de trabajo: escrito, expuesto, con
    respuesta de exito prevista, y sin un solo camino que llegue a ella.

    ## El ambito, que tampoco estaba

    No habia ninguna comprobacion de a quien pertenece el proveedor, mientras su
    vecino `list_discovery_jobs` **si** la hace y lo dice en un comentario. Con
    la consulta arreglada eso pasaria de inocuo a una **escritura cruzada entre
    clientes**: aprobar la linea base de los CIs de otro cliente le quita la
    marca de deriva, es decir le apaga una alerta de configuracion.

    Se resuelve el proveedor con `org_scoped_or_404`, y los CIs se acotan
    ademas por organizacion siguiendo la politica ya establecida en
    `app/core/tenancy.py`: una fila con `organization_id` a NULL es dato
    legacy/global y se considera accesible.

    ## Dos proveedores del mismo tipo

    Desde la migracion 110 el CI guarda tambien **cual** proveedor lo
    descubrio (`discovery_provider_id`), y se aprueba solo lo suyo. Los CIs
    descubiertos antes, sin ese dato, se siguen casando por el tipo hasta que
    el siguiente escaneo lo rellene.
    """
    from app.core.tenancy import org_scoped_or_404
    from app.models.cmdb import CMDBDiscoveryProvider

    proveedor = org_scoped_or_404(
        db, CMDBDiscoveryProvider, provider_id, current_user,
        detail="Provider not found")

    q = db.query(ConfigurationItem).filter(
        ConfigurationItem.discovery_provider == proveedor.provider_type,
        (ConfigurationItem.discovery_provider_id == proveedor.id)
        | (ConfigurationItem.discovery_provider_id.is_(None)))

    if not getattr(current_user, "is_superadmin", False):
        org_id = getattr(current_user, "organization_id", None)
        if org_id is None:
            # Sin organizacion, sin acceso: la misma politica que `_can_access`.
            return {"ok": False, "error": "No CIs found for provider/ci_id combination"}
        q = q.filter(
            (ConfigurationItem.organization_id == org_id)
            | (ConfigurationItem.organization_id.is_(None))
        )

    if ci_id:
        q = q.filter(ConfigurationItem.id == ci_id)

    cis = q.all()
    if not cis:
        return {"ok": False, "error": "No CIs found for provider/ci_id combination"}

    for ci in cis:
        ci.baseline_attributes = ci.attributes
        ci.drift_detected_at = None

    return {"ok": True, "approved": len(cis)}


def get_drift_report(db: Session, hours: int = 24, org_id: str | None = None) -> dict:
    """Return CIs where config drift was detected in the last `hours` hours.

    For each drifted CI, include the most recent changelog entries for that CI.

    Returns a dict suitable for the REST drift-report endpoint.
    """
    cutoff = utcnow() - timedelta(hours=max(1, hours))

    drifted = (
        _de_la_organizacion(db.query(ConfigurationItem), org_id)
        .filter(
            ConfigurationItem.drift_detected_at >= cutoff,
            ConfigurationItem.is_discovered.is_(True),
        )
        .order_by(ConfigurationItem.drift_detected_at.desc())
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
                "ci_type": ci.ci_type.value if ci.ci_type else None,
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


def get_reconciliation_health(db: Session, provider_type: str | None = None,
                              org_id: str | None = None) -> dict:
    """Build reconciliation health metrics for discovered CIs.

    Metrics:
      - total_discovered: discovered CIs in CMDB
      - active_discovered: discovered CIs currently active/maintenance
      - stale_discovered: discovered CIs retired by reconciliation
      - duplicate_external_ids: repeated (provider, external_id) pairs
      - by_provider: per-provider counts
    """
    q = _de_la_organizacion(db.query(ConfigurationItem), org_id).filter(
        ConfigurationItem.is_discovered.is_(True))
    if provider_type:
        q = q.filter(ConfigurationItem.discovery_provider == provider_type)

    rows = q.all()
    total_discovered = len(rows)
    stale_discovered = sum(1 for r in rows if r.status == _RETIRADO)
    active_discovered = total_discovered - stale_discovered

    dup_q = (
        _de_la_organizacion(db.query(
            ConfigurationItem.discovery_provider,
            ConfigurationItem.external_id,
            func.count(ConfigurationItem.id).label("n"),
        ), org_id)
        .filter(ConfigurationItem.is_discovered.is_(True), ConfigurationItem.external_id.isnot(None))
        .group_by(ConfigurationItem.discovery_provider, ConfigurationItem.external_id)
        .having(func.count(ConfigurationItem.id) > 1)
    )
    if provider_type:
        dup_q = dup_q.filter(ConfigurationItem.discovery_provider == provider_type)

    duplicate_external_ids = dup_q.count()

    provider_counts = {}
    for r in rows:
        key = r.discovery_provider or "unknown"
        if key not in provider_counts:
            provider_counts[key] = {
                "total": 0,
                "active": 0,
                "retired": 0,
            }
        provider_counts[key]["total"] += 1
        if r.status == _RETIRADO:
            provider_counts[key]["retired"] += 1
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

def ci_similarity_score(ci_a: ConfigurationItem, ci_b: ConfigurationItem) -> float:
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
    org_id: str | None = None,
) -> list[dict]:
    """Posibles duplicados con su confianza. Nunca entre organizaciones."""
    q = _de_la_organizacion(db.query(ConfigurationItem), org_id).filter(
        ConfigurationItem.is_discovered.is_(True), ConfigurationItem.status != _RETIRADO)
    if provider_type:
        q = q.filter(ConfigurationItem.discovery_provider == provider_type)
    rows = q.order_by(ConfigurationItem.discovery_provider.asc(), ConfigurationItem.name.asc()).all()

    candidates: list[dict] = []
    for i in range(len(rows)):
        a = rows[i]
        for j in range(i + 1, len(rows)):
            b = rows[j]
            if provider_type and (a.discovery_provider != b.discovery_provider):
                continue
            if a.organization_id != b.organization_id:
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
    org_id: str | None = None,
) -> dict:
    """Retira los duplicados probables, dentro de una misma organizacion."""
    candidates = deduplicate_candidates(
        db,
        provider_type=provider_type,
        min_confidence=min_confidence,
        org_id=org_id,
    )[: max(1, limit)]

    merged = 0
    applied: list[dict] = []
    for c in candidates:
        dup = db.get(ConfigurationItem, c["duplicate"]["id"])
        keep = db.get(ConfigurationItem, c["keeper"]["id"])
        if not dup or not keep or dup.status == _RETIRADO:
            continue

        dup.status = _RETIRADO
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
    organization_id: str | None = None,
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
    from app.models.cmdb import CMDBAgentRegistration

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
        organization_id=organization_id,
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


def _agentes(db: Session, org_id: str | None):
    """Los agentes de una organizacion; `None` es el superadministrador."""
    from app.models.cmdb import CMDBAgentRegistration

    q = db.query(CMDBAgentRegistration)
    return q if org_id is None else q.filter(CMDBAgentRegistration.organization_id == org_id)


def list_agent_registrations(db: Session, org_id: str | None = None) -> list[dict]:
    """Return agent registrations with last check-in info."""
    from app.models.cmdb import CMDBAgentRegistration

    rows = _agentes(db, org_id).order_by(CMDBAgentRegistration.created_at.desc()).all()
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


def revoke_agent_token(db: Session, agent_id: str, org_id: str | None = None) -> None:
    """Deactivate an agent registration (revoke its token)."""
    from app.models.cmdb import CMDBAgentRegistration

    reg = _agentes(db, org_id).filter(CMDBAgentRegistration.id == agent_id).first()
    if not reg:
        raise ErrorDeDominio(status_code=404, detail=f"Agent {agent_id} not found")
    reg.is_active = False
    db.flush()


def rotate_agent_token(db: Session, agent_id: str, org_id: str | None = None) -> dict:
    """Generate a new token for an agent registration.

    The old token is immediately invalidated.  Returns the new raw token once.
    """
    from app.models.cmdb import CMDBAgentRegistration

    reg = _agentes(db, org_id).filter(CMDBAgentRegistration.id == agent_id).first()
    if not reg:
        raise ErrorDeDominio(status_code=404, detail=f"Agent {agent_id} not found")

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
    from app.services.cmdb.parser import resolve_agent_by_token, normalize_agent_payload

    reg = resolve_agent_by_token(db, raw_token)
    if not reg:
        raise ErrorDeDominio(status_code=401, detail="Invalid or revoked agent token")
    # Segunda auditoría 2026-11 (#10): organización desactivada → 403.
    from app.db.session import exigir_organizacion_activa
    exigir_organizacion_activa(db, reg.organization_id)

    ci_dict = normalize_agent_payload(payload, reg.id)

    # Solo este host: los demas agentes no estan ausentes, simplemente no
    # les toca ahora.
    stats = reconcile_cis(db, [ci_dict], PROVIDER_AGENT,
                          organization_id=reg.organization_id, retirar_ausentes=False)

    ci = (
        db.query(ConfigurationItem)
        .filter(
            ConfigurationItem.external_id == ci_dict["external_id"],
            ConfigurationItem.discovery_provider == PROVIDER_AGENT,
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
