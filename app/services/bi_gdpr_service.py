"""
bi_gdpr_service.py — GDPR compliance for BI data.

Handles:
  - Data erasure requests (DSR) — anonymises personal data in DB + analytics snapshots
  - Portability requests (DSR) — exports all data for a subject as JSON
  - Rectification requests (DSR) — marks for manual data correction
  - Restriction requests (DSR) — marks processing restriction
  - Consent management — track which users have consented to BI analytics collection
    with full audit history per user
  - DSR (Data Subject Request) status tracking
  - Field-level data masking metadata
  - Dashboard stats (pending DSRs, total consents, SLA breach detection)

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
import logging

logger = logging.getLogger(__name__)

_KEY_CONSENT = "bi.gdpr.consent"
_KEY_CONSENT_HISTORY = "bi.gdpr.consent_history"
_KEY_DSR = "bi.gdpr.dsr"
_KEY_MASKS = "bi.gdpr.field_masks"

def _plazo_dsr(db: Session, org_id: Optional[str]) -> int:
    """Plazo de una solicitud RGPD (art. 12.3): `COMPLIANCE_GDPR_MAX_DAYS` de Admin.

    Revisión 2026-11: era una constante de 30 días aquí y el ajuste sólo lo
    usaba el informe de cumplimiento.
    """
    from app.services.settings_service import get_runtime_int
    return int(get_runtime_int(db, "COMPLIANCE_GDPR_MAX_DAYS", org_id))


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
        logger.debug("_get_setting: excepcion ignorada", exc_info=True)
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

def record_consent(
    db: Session,
    *,
    user_id: str,
    consented: bool,
    org_id: Optional[str],
    purpose: str = "analytics",
    channel: str = "web",
    ip_address: Optional[str] = None,
) -> dict:
    """Record or revoke BI analytics consent for a user. Appends to audit history."""
    now = _iso_now()
    entry = {
        "user_id": user_id,
        "consented": consented,
        "granted": consented,
        "purpose": purpose,
        "channel": channel,
        "updated_at": now,
    }
    consents: dict = _consentimientos(db, org_id)
    consents.setdefault(user_id, {})[purpose] = entry
    _set_setting(db, _KEY_CONSENT, org_id, consents)

    # Append to per-user audit history
    history: dict = _get_setting(db, _KEY_CONSENT_HISTORY, org_id, {})
    user_hist: list = history.get(user_id, [])
    user_hist.append({
        "action": "granted" if consented else "revoked",
        "purpose": purpose,
        "channel": channel,
        "ip_address": ip_address,
        "timestamp": now,
    })
    # Keep last 100 history entries per user
    history[user_id] = user_hist[-100:]
    _set_setting(db, _KEY_CONSENT_HISTORY, org_id, history)

    return entry


def _consentimientos(db: Session, org_id: Optional[str]) -> dict:
    """{usuario: {propósito: registro}}.

    Revisión 2026-11: se guardaba uno por usuario y un consentimiento para otro
    propósito pisaba el anterior. Lo guardado con la forma antigua (un registro
    por usuario) se lee convertido.
    """
    crudo: dict = _get_setting(db, _KEY_CONSENT, org_id, {}) or {}
    return {u: ({v.get("purpose") or "analytics": v} if isinstance(v, dict) and "user_id" in v else dict(v or {}))
            for u, v in crudo.items()}


def get_consent(db: Session, *, user_id: str, org_id: Optional[str], purpose: str = "analytics") -> Optional[dict]:
    return _consentimientos(db, org_id).get(user_id, {}).get(purpose)


def list_consents(db: Session, *, org_id: Optional[str]) -> list[dict]:
    return [e for por_proposito in _consentimientos(db, org_id).values() for e in por_proposito.values()]


def get_consent_history(db: Session, *, user_id: str, org_id: Optional[str]) -> list[dict]:
    """Return the full audit trail of consent changes for a user."""
    history = _get_setting(db, _KEY_CONSENT_HISTORY, org_id, {})
    return list(reversed(history.get(user_id, [])))


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
    Create a new DSR (erasure, portability, rectification, restriction).
    Adds SLA deadline (`COMPLIANCE_GDPR_MAX_DAYS`) per GDPR Art. 12.3.
    """
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    deadline = (now + timedelta(days=_plazo_dsr(db, org_id))).isoformat()
    dsrs: dict = _get_setting(db, _KEY_DSR, org_id, {})
    dsr_id = str(uuid.uuid4())
    entry = {
        "id": dsr_id,
        "subject_id": subject_id,
        "request_type": request_type,
        "status": "pending",
        "requester_user_id": requester_user_id,
        "notes": notes,
        "created_at": now.isoformat(),
        "deadline": deadline,
        "resolved_at": None,
        "resolution_notes": None,
        "export_data": None,
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
    execute_erasure_pipeline: bool = False,
) -> dict:
    dsrs: dict = _get_setting(db, _KEY_DSR, org_id, {})
    if dsr_id not in dsrs:
        raise ValueError(f"DSR '{dsr_id}' not found")
    dsrs[dsr_id]["status"] = "completed"
    dsrs[dsr_id]["resolved_at"] = _iso_now()
    dsrs[dsr_id]["resolution_notes"] = resolution_notes
    _set_setting(db, _KEY_DSR, org_id, dsrs)

    # Borrado. Revisión 2026-11: antes se registraba primero la revocación, que
    # volvía a escribir el identificador del interesado en consentimientos e
    # historial justo antes de borrar. Con el borrado, se borra todo y la
    # solicitud guarda el identificador seudonimizado; sin él, sólo se revoca.
    if dsrs[dsr_id]["request_type"] == "erasure":
        sujeto = dsrs[dsr_id]["subject_id"]
        if execute_erasure_pipeline:
            report = execute_erasure(db, subject_id=sujeto, org_id=org_id)
            report["subject_id"] = _anon_hash(sujeto)
            dsrs[dsr_id]["erasure_report"] = report
            dsrs[dsr_id]["subject_id"] = _anon_hash(sujeto)
            _set_setting(db, _KEY_DSR, org_id, dsrs)
        else:
            record_consent(db, user_id=sujeto, consented=False, org_id=org_id)

    return dsrs[dsr_id]


def list_dsrs(db: Session, *, org_id: Optional[str], status: Optional[str] = None) -> list[dict]:
    dsrs = list(_get_setting(db, _KEY_DSR, org_id, {}).values())
    if status:
        dsrs = [d for d in dsrs if d["status"] == status]
    return sorted(dsrs, key=lambda d: d["created_at"], reverse=True)


def get_dsr_stats(db: Session, *, org_id: Optional[str]) -> dict:
    """Return dashboard summary: pending count, overdue DSRs, consent totals."""
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    dsrs = list(_get_setting(db, _KEY_DSR, org_id, {}).values())
    pending = [d for d in dsrs if d["status"] == "pending"]
    completed = [d for d in dsrs if d["status"] == "completed"]
    # SLA breach: pending DSRs past deadline
    plazo = _plazo_dsr(db, org_id)
    overdue = []
    for d in pending:
        deadline_str = d.get("deadline")
        created_str = d.get("created_at", "")
        try:
            if deadline_str:
                dl = datetime.fromisoformat(deadline_str)
            else:
                dl = datetime.fromisoformat(created_str) + timedelta(days=plazo)
            if dl.tzinfo is None:
                dl = dl.replace(tzinfo=timezone.utc)
            if now > dl:
                overdue.append(d)
        # intentional: best-effort fallback, log noise outweighs diagnostic value
        except Exception:
            logger.debug("get_dsr_stats: fallo best-effort ignorado", exc_info=True)
    consents = list_consents(db, org_id=org_id)
    consented_count = sum(1 for c in consents if c.get("consented"))
    by_type: dict[str, int] = {}
    for d in dsrs:
        by_type[d["request_type"]] = by_type.get(d["request_type"], 0) + 1
    return {
        "total_dsrs": len(dsrs),
        "pending": len(pending),
        "completed": len(completed),
        "overdue": len(overdue),
        "overdue_ids": [d["id"] for d in overdue],
        "by_type": by_type,
        "total_consents": len(consents),
        "consented": consented_count,
        "revoked": len(consents) - consented_count,
    }


def get_dsr(db: Session, *, dsr_id: str, org_id: Optional[str]) -> Optional[dict]:
    dsrs: dict = _get_setting(db, _KEY_DSR, org_id, {})
    return dsrs.get(dsr_id)


def execute_portability(db: Session, *, subject_id: str, org_id: Optional[str]) -> dict:
    """
    Generate a portable data export (JSON) for *subject_id* covering:
      - User profile fields
      - Tickets as requester
      - Consent history

    Returns an export package dict suitable for download.
    Does NOT delete any data.
    """
    from app.models.user import User
    from app.models.service_desk import Ticket

    export: dict[str, Any] = {
        "export_type": "portability",
        "subject_id": subject_id,
        "generated_at": _iso_now(),
        "data": {},
    }

    # ── User profile ──────────────────────────────────────────────────────────
    user_q = db.query(User)
    if "@" in subject_id:
        user = user_q.filter(User.email == subject_id).first()
    else:
        user = user_q.filter(User.id == subject_id).first()

    if user:
        export["data"]["profile"] = {
            "id": user.id,
            "email": user.email,
            "username": getattr(user, "username", None),
            "full_name": getattr(user, "full_name", None),
            "first_name": getattr(user, "first_name", None),
            "last_name": getattr(user, "last_name", None),
            "role": getattr(user, "role", None),
            "created_at": str(getattr(user, "created_at", "")),
        }
        user_id_for_query = user.id
    else:
        export["data"]["profile"] = None
        user_id_for_query = subject_id

    # ── Tickets ───────────────────────────────────────────────────────────────
    tickets = db.query(Ticket).filter(
        (Ticket.requester_user_id == user_id_for_query) |
        (Ticket.requester_email == subject_id)
    ).all()
    export["data"]["tickets"] = [
        {
            "id": t.id,
            "number": getattr(t, "number", None),
            "title": getattr(t, "title", None),
            "status": str(getattr(t, "status", "")),
            "created_at": str(getattr(t, "created_at", "")),
        }
        for t in tickets
    ]

    # ── Consent history ───────────────────────────────────────────────────────
    export["data"]["consent_history"] = get_consent_history(db, user_id=subject_id, org_id=org_id)

    # ── Current consent ───────────────────────────────────────────────────────
    export["data"]["current_consent"] = get_consent(db, user_id=subject_id, org_id=org_id)

    return export


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


def aplicar_mascaras(db: Session, org_id: Optional[str], dataset: str, filas: list) -> list:
    """Aplica las máscaras de campo de `dataset` a las filas (revisión 2026-11).

    Se guardaban y nada las aplicaba. Ahora el motor de informes —constructor,
    Explorador de datos y exportación CSV— pasa por aquí.
    """
    mascaras = {m["field"]: m["mask_type"] for m in (_get_setting(db, _KEY_MASKS, org_id, {}) or {}).values()
                if m.get("dataset") == dataset}
    if not mascaras:
        return filas
    for fila in filas:
        for campo, tipo in mascaras.items():
            if campo in fila and fila[campo] not in (None, ""):
                fila[campo] = (None if tipo == "suppress" else "***" if tipo == "redact"
                               else _anon_hash(str(fila[campo])))
    return filas


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

    user_id_for_tickets = user.id if user else subject_id
    original_email = user.email if user else subject_id
    # ── Anonymise ticket requester fields ─────────────────────────────────────
    tickets = db.query(Ticket).filter(
        (Ticket.requester_user_id == user_id_for_tickets) |
        (Ticket.requester_email == original_email)
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

    # ── La persona: ficha, copias exactas en todas las tablas, credenciales y almacén ──
    if user:
        from app.services.supresion_service import suprimir_persona
        detalle = suprimir_persona(db, user)
        report["operations"].append({"table": "users", "row_id": user.id, "action": "anonymised"})
        report["operations"] += [{"table": t, "count": n, "action": "anonymised"} for t, n in detalle["tablas"].items()]
        report["operations"] += [{"table": t, "count": n, "action": "deleted"} for t, n in detalle["credenciales"].items()]
        report["operations"].append({"table": "duckdb", "action": detalle["almacen"]})

    # ── Purge analytics consent & DSR snapshot (no historical PII) ───────────
    claves = {subject_id} | ({user.id} if user else set())
    for clave_ajuste, nombre in ((_KEY_CONSENT, "consent"), (_KEY_CONSENT_HISTORY, "consent_history")):
        datos: dict = _get_setting(db, clave_ajuste, org_id, {}) or {}
        quitadas = [k for k in claves if k in datos]
        for k in quitadas:
            del datos[k]
        if quitadas:
            _set_setting(db, clave_ajuste, org_id, datos)
            report["operations"].append({"table": f"appsetting[bi.gdpr.{nombre}]", "action": "deleted"})

    db.commit()
    return report
