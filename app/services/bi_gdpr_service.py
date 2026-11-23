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
from app.core.codigos_de_error import ErrorConCodigo

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
        "ip_address": _ip_minimizada(ip_address),
        "timestamp": now,
    })
    # M55 (auditoría 22-11-2026): historial COMPLETO. Antes se quedaban las
    # últimas 100 entradas y el art. 7.1 RGPD exige poder demostrar el
    # consentimiento (también el primero). La IP se guarda truncada (/24 y /48):
    # basta para la prueba y no identifica el equipo.
    history[user_id] = user_hist
    _set_setting(db, _KEY_CONSENT_HISTORY, org_id, history)

    return entry


def _ip_minimizada(ip: Optional[str]) -> Optional[str]:
    """M55: IPv4 a /24 y IPv6 a /48 (minimización, art. 5.1.c RGPD)."""
    if not ip:
        return None
    import ipaddress
    try:
        dir_ = ipaddress.ip_address(ip.strip())
    except ValueError:
        return None
    red = ipaddress.ip_network(f"{dir_}/{24 if dir_.version == 4 else 48}", strict=False)
    return str(red)


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

# ── Un solo registro de solicitudes RGPD (auditoría 22-11-2026, A60 + 05·H5) ──
#
# `/bi/gdpr/dsr` llevaba un registro PARALELO (blob JSON en `AppSetting`) al de
# `/gdpr/requests` (tabla `gdpr_requests`, `cab_service/gdpr.py`): las
# solicitudes de un interesado quedaban repartidas, la supresión se marcaba
# «completed» ANTES de borrar (y también si no se borraba: la vía sin
# `execute_erasure_pipeline` solo revocaba el consentimiento), y rectificación
# y restricción se aceptaban sin aplicarse. Ahora:
#
# - las solicitudes NUEVAS se crean en `gdpr_requests` (el registro único) y se
#   resuelven con `cab_service.gdpr.process_gdpr_request` (el mismo circuito:
#   bloqueo legal, supresión completa, copia cifrada con caducidad);
# - `restriction` no tiene circuito: se rechaza con 422 (`rgpd_tipo_no_soportado`);
# - las antiguas del blob se siguen listando y resolviendo, pero una supresión
#   solo se marca completada DESPUÉS de borrar, y nunca sin borrar.

_TIPOS_CANONICOS = ("erasure", "portability", "rectification")


def _canonica(db: Session, dsr_id: str, org_id: Optional[str]):
    from app.models.cab import GDPRRequest
    q = db.query(GDPRRequest).filter(GDPRRequest.id == dsr_id)
    if org_id:
        q = q.filter(GDPRRequest.organization_id == org_id)
    return q.first()


def _de_canonica(r) -> dict:
    return {
        "id": r.id,
        "subject_id": r.subject_user_id or r.subject_email,
        "request_type": getattr(r.request_type, "value", r.request_type),
        "status": getattr(r.status, "value", r.status),
        "requester_user_id": r.requestor_id,
        "notes": r.notes,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        # Fecha y hora (la del alta) para que plazo − alta dé los días del plazo.
        "deadline": (datetime.combine(r.deadline, r.created_at.time()).isoformat()
                     if r.deadline and r.created_at else (str(r.deadline) if r.deadline else None)),
        "resolved_at": r.completed_at.isoformat() if r.completed_at else None,
        "resolution_notes": None,
        "export_data": None,
        "registro": "gdpr_requests",
    }


def create_dsr(
    db: Session,
    *,
    subject_id: str,
    request_type: str,
    org_id: Optional[str],
    requester_user_id: str,
    notes: Optional[str] = None,
) -> dict:
    """Alta de una solicitud del interesado.

    Si el interesado es una persona de la empresa (y quien pide, un usuario),
    va al registro ÚNICO (`gdpr_requests`) y se resuelve por su circuito. Si es
    solo un identificador de consentimiento de BI (no una persona de la
    aplicación), queda en el registro de BI, con las mismas reglas: la
    supresión solo se completa ejecutándola. `restriction` → 422.
    """
    if request_type == "restriction":
        raise ErrorConCodigo("rgpd_tipo_no_soportado", tipo=request_type)
    from types import SimpleNamespace
    from app.models.cab import GDPRRequest, GDPRRequestType
    from app.models.user import User
    q_sujeto = db.query(User.id).filter(User.id == subject_id)
    if org_id:
        q_sujeto = q_sujeto.filter(User.organization_id == org_id)
    solicitante = db.query(User).filter(User.id == requester_user_id).first()
    if request_type in _TIPOS_CANONICOS and solicitante is not None and q_sujeto.first() is not None:
        from app.services.cab_service.gdpr import create_gdpr_request
        payload = SimpleNamespace(request_type=GDPRRequestType(request_type), subject_user_id=subject_id,
                                  subject_email=None, notes=notes)
        res = create_gdpr_request(payload, solicitante, db)
        return _de_canonica(db.query(GDPRRequest).filter(GDPRRequest.id == res["id"]).first())

    from datetime import timedelta
    now = datetime.now(timezone.utc)
    dsrs: dict = _get_setting(db, _KEY_DSR, org_id, {})
    dsr_id = str(uuid.uuid4())
    dsrs[dsr_id] = {
        "id": dsr_id, "subject_id": subject_id, "request_type": request_type, "status": "pending",
        "requester_user_id": requester_user_id, "notes": notes, "created_at": now.isoformat(),
        "deadline": (now + timedelta(days=_plazo_dsr(db, org_id))).isoformat(),
        "resolved_at": None, "resolution_notes": None, "export_data": None,
    }
    _set_setting(db, _KEY_DSR, org_id, dsrs)
    return dsrs[dsr_id]


def completar_con_copia(db: Session, *, dsr_id: str, org_id: Optional[str], actor, copia: dict) -> dict:
    """Completa una solicitud del registro único guardando su copia (cifrada, con caducidad)."""
    from app.models.cab import GDPRRequestStatus
    from app.services.audit import audit_log
    from app.services.cab_service.gdpr import _guardar_copia
    req = _canonica(db, dsr_id, org_id)
    if req is None:
        raise ErrorConCodigo("no_encontrado", que="solicitud_rgpd")
    req.status = GDPRRequestStatus.completed
    req.completed_at = datetime.now(timezone.utc)
    req.processed_by = getattr(actor, "id", None)
    _guardar_copia(req, copia)
    audit_log(db, actor, "GDPR_PROCESS", "users", req.subject_user_id or "unknown", "",
              new_values={"type": getattr(req.request_type, "value", req.request_type), "result": "completed"})
    db.commit()
    return _de_canonica(req)


def resolve_dsr(
    db: Session,
    *,
    dsr_id: str,
    org_id: Optional[str],
    resolution_notes: Optional[str] = None,
    execute_erasure_pipeline: bool = False,
    actor=None,
) -> dict:
    canonica = _canonica(db, dsr_id, org_id)
    if canonica is not None:
        tipo = getattr(canonica.request_type, "value", canonica.request_type)
        if tipo == "erasure" and not execute_erasure_pipeline:
            # A60: una supresión no se «resuelve» sin borrar.
            raise ErrorConCodigo("rgpd_borrado_sin_ejecutar")
        if actor is None:
            raise ErrorConCodigo("sin_permiso")
        from app.services.cab_service.gdpr import process_gdpr_request
        res = process_gdpr_request(canonica.id, actor, db)
        db.refresh(canonica)
        entrada = _de_canonica(canonica)
        entrada["resolution_notes"] = resolution_notes
        if tipo == "erasure":
            entrada["erasure_report"] = res.get("data")
        else:
            entrada["export_data"] = res.get("data")
        return entrada

    dsrs: dict = _get_setting(db, _KEY_DSR, org_id, {})
    if dsr_id not in dsrs:
        raise ErrorConCodigo("no_encontrado", detail=f"DSR '{dsr_id}' not found", que="solicitud_rgpd")

    # Borrado. Revisión 2026-11: antes se registraba primero la revocación, que
    # volvía a escribir el identificador del interesado en consentimientos e
    # historial justo antes de borrar. Con el borrado, se borra todo y la
    # solicitud guarda el identificador seudonimizado.
    # Auditoría 22-11-2026 (A60): se borra PRIMERO y solo después se marca
    # completada; sin ejecutar el borrado, una supresión no se cierra.
    if dsrs[dsr_id]["request_type"] == "erasure":
        if not execute_erasure_pipeline:
            raise ErrorConCodigo("rgpd_borrado_sin_ejecutar")
        if actor is not None:
            from app.models.user import User
            from app.services.supresion_service import exigir_sin_bloqueo_legal
            sujeto_u = db.query(User).filter(User.id == dsrs[dsr_id]["subject_id"]).first()
            if sujeto_u is not None:
                exigir_sin_bloqueo_legal(db, sujeto_u)
        sujeto = dsrs[dsr_id]["subject_id"]
        report = execute_erasure(db, subject_id=sujeto, org_id=org_id)
        report["subject_id"] = _anon_hash(sujeto)
        dsrs[dsr_id]["erasure_report"] = report
        dsrs[dsr_id]["subject_id"] = _anon_hash(sujeto)
    elif dsrs[dsr_id]["request_type"] == "restriction":
        raise ErrorConCodigo("rgpd_tipo_no_soportado", tipo="restriction")

    dsrs[dsr_id]["status"] = "completed"
    dsrs[dsr_id]["resolved_at"] = _iso_now()
    dsrs[dsr_id]["resolution_notes"] = resolution_notes
    _set_setting(db, _KEY_DSR, org_id, dsrs)
    return dsrs[dsr_id]


def list_dsrs(db: Session, *, org_id: Optional[str], status: Optional[str] = None) -> list[dict]:
    """Las del registro único (`gdpr_requests`) y las antiguas del blob de BI."""
    from app.models.cab import GDPRRequest
    q = db.query(GDPRRequest)
    if org_id:
        q = q.filter(GDPRRequest.organization_id == org_id)
    dsrs = [_de_canonica(r) for r in q.all()] + list(_get_setting(db, _KEY_DSR, org_id, {}).values())
    if status:
        dsrs = [d for d in dsrs if d["status"] == status]
    return sorted(dsrs, key=lambda d: d.get("created_at") or "", reverse=True)


def get_dsr_stats(db: Session, *, org_id: Optional[str]) -> dict:
    """Return dashboard summary: pending count, overdue DSRs, consent totals."""
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    dsrs = list_dsrs(db, org_id=org_id)
    pending = [d for d in dsrs if d["status"] in ("pending", "processing")]
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
    canonica = _canonica(db, dsr_id, org_id)
    if canonica is not None:
        return _de_canonica(canonica)
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

    # M55 (auditoría 22-11-2026): portabilidad (art. 20) con los datos que la
    # persona aporta en el uso normal: imputaciones, gastos y ausencias (antes
    # solo ficha, tickets y consentimiento).
    if user:
        from app.models.expenses import Expense
        from app.models.imputation import Imputation
        from app.models.resources import Absence
        export["data"]["time_entries"] = [
            {"date": str(i.date), "hours": i.hours, "project_id": i.project_id, "description": i.description}
            for i in db.query(Imputation).filter(Imputation.user_id == user.id, Imputation.is_active.is_(True)).all()]
        export["data"]["expenses"] = [
            {"date": str(e.expense_date), "amount": e.amount, "currency": e.currency,
             "category": str(getattr(e.category, "value", e.category)), "description": e.description}
            for e in db.query(Expense).filter(Expense.user_id == user.id, Expense.is_active.isnot(False)).all()]
        export["data"]["absences"] = [
            {"start": str(a.start_date), "end": str(a.end_date), "type": a.type,
             "status": str(getattr(a.status, "value", a.status))}
            for a in db.query(Absence).filter(Absence.user_id == user.id, Absence.is_active.is_(True)).all()]

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
    """Seudónimo de un solo sentido CON CLAVE.

    M55 (auditoría 22-11-2026): era SHA-256 sin sal a 12 hex: con la lista de
    correos de la empresa se deshacía por fuerza bruta. Ahora HMAC-SHA256 con la
    clave del servidor (16 hex): sin la clave no se puede recomputar.
    """
    import hmac
    from app.core.config import settings
    return "[erased:" + hmac.new(str(settings.SECRET_KEY).encode(), value.encode(),
                                  hashlib.sha256).hexdigest()[:16] + "]"


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

    if user:   # segunda auditoría 2026-11: bajo bloqueo legal no se reescribe nada (409)
        from app.services.supresion_service import exigir_sin_bloqueo_legal
        exigir_sin_bloqueo_legal(db, user)
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
