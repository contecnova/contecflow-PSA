"""
AI Auto-Resolution Service — Inteligent ticket resolution using IA + KB + ML.

Capabilidades:
  - Análisis automático de tickets con scoring compuesto (AI + KB + histórico)
  - Búsqueda en KB + reglas
  - Sugerencias de resolución con score de confianza
  - Auto-resolución si confianza compuesta > threshold
  - Post-resolution validation: detecta reaperturas → penaliza scoring
  - Feedback loop: acumula tasas de éxito por categoría/prioridad en AppSetting
  - Auto-close job: cierra tickets resueltos sin respuesta tras N horas
  - Audit trail completo
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.service_desk import Ticket, TicketStatus, KBArticle, KBStatus
from app.services.ai_provider_service import call_ai

_logger = logging.getLogger("ai_auto_resolution")

# ── Auto-resolution confidence thresholds ────────────────────────────────────
# Item #60: estos valores son **defaults conservadores** y se solapan con la
# config dinámica (``AUTO_CONFIG_SETTING_KEY``) por organización. Auto a 0.85
# es deliberadamente alto — confiar al 85% en un LLM para cerrar sin revisión
# humana ya es una apuesta fuerte. Si una org necesita más prudencia, debe
# subirlo vía settings (ej. 0.95) en lugar de bajar este default. Bajar más
# de 0.85 sin telemetría de tasa de reapertura es desaconsejable.
CONFIDENCE_THRESHOLD_AUTO = 0.85     # Auto-resolve if composite >= 85%
CONFIDENCE_THRESHOLD_SUGGEST = 0.65  # Show suggestion if composite >= 65%

# ── Feedback loop config ─────────────────────────────────────────────────────
FEEDBACK_SETTING_KEY = "sd.auto_resolution.feedback_stats"  # legacy key (org-less)
FEEDBACK_SETTING_KEY_TEMPLATE = "sd.auto_resolution.feedback_stats::{org}"
AUTO_CLOSE_HOURS_AFTER_RESOLUTION = 72  # Auto-close resolved tickets after 72h
VALIDATION_WINDOW_HOURS = 48            # Check for reopens within 48h
AUTO_CONFIG_SETTING_KEY = "sd.auto_resolution.config"           # legacy key (org-less)
AUTO_CONFIG_SETTING_KEY_TEMPLATE = "sd.auto_resolution.config::{org}"

# ── Estado y historial del trabajo, por organizacion ────────────────────────
#
# Auditoria 2026-08 (P3-22, tanda 2). Estas tres cosas vivian en el endpoint con
# claves de `AppSetting` **sin organizacion**, asi que eran globales: un cliente
# veia el `job_id`, los tiempos, las estadisticas y los errores del trabajo de
# otro, y cualquier administrador cambiaba los umbrales de todos. El comentario
# de cabecera de este modulo ya decia que la config es «por organizacion»: la
# intencion estaba escrita y el codigo no la cumplia.
#
# Se sigue la convencion que este modulo ya tenia para el contador de feedback
# —`clave::{org}` con respaldo en la clave desnuda— en vez de inventar otra. El
# respaldo importa: en un despliegue en marcha ya hay filas bajo la clave sin
# organizacion, y leerlas es lo que evita perder la configuracion al desplegar.
JOB_RUNTIME_KEY_LEGACY = "sd.auto_resolution.job_runtime"   # sin organizacion
JOB_HISTORY_KEY_LEGACY = "sd.auto_resolution.job_history"   # sin organizacion
JOB_RUNTIME_KEY_TEMPLATE = "sd.auto_resolution.job_runtime::{org}"
JOB_HISTORY_KEY_TEMPLATE = "sd.auto_resolution.job_history::{org}"

#: Cuantas ejecuciones se conservan. Es un `AppSetting`, no una tabla de
#: eventos: sin tope la fila crece sin freno y se lee entera en cada consulta.
MAX_HISTORIAL_DEL_TRABAJO = 20

#: Marcador de organizacion para las claves cuando no hay ninguna.
_SIN_ORGANIZACION = "global"

_CERROJOS_DEL_TRABAJO: dict[str, threading.Lock] = {}
_GUARDA_DE_CERROJOS = threading.Lock()


def cerrojo_del_trabajo(organization_id: str | None) -> threading.Lock:
    """El cerrojo del trabajo de auto-resolucion de esa organizacion.

    Auditoria 2026-08: era `_AUTO_RES_JOB_LOCK = Lock()` a nivel de modulo, uno
    para todo el proceso, asi que con el trabajo de un cliente en marcha el de
    otro recibia `already_running` y no podia ejecutar el suyo.

    Sigue siendo un cerrojo **en proceso**, con lo que no coordina entre varios
    workers de Uvicorn: dos procesos pueden lanzar el trabajo de la misma
    organizacion a la vez. Para eso hace falta un cerrojo distribuido, y no se
    monta aqui de paso; lo que se corrige es que uno solo bloqueaba a todos.
    """
    clave = organization_id or _SIN_ORGANIZACION
    with _GUARDA_DE_CERROJOS:
        cerrojo = _CERROJOS_DEL_TRABAJO.get(clave)
        if cerrojo is None:
            cerrojo = threading.Lock()
            _CERROJOS_DEL_TRABAJO[clave] = cerrojo
        return cerrojo


def _clave_por_organizacion(
    plantilla: str, organization_id: str | None, heredada: str | None = None,
) -> str:
    """La clave de ese dato para esa organizacion.

    Sin organizacion se devuelve la clave **heredada** —la desnuda, sin sufijo—
    cuando existe, y no `::global`. No es cosmetico: en un despliegue en marcha
    los valores ya estan guardados bajo la clave desnuda, y una ejecucion de
    plataforma (`organization_id=None`) tiene que leer y escribir esos mismos, no
    una fila nueva y vacia. Al escribir y al leer se usa esta misma funcion, que
    es lo que faltaba: guardaba en una clave y leia de otra.
    """
    if organization_id is None and heredada:
        return heredada
    return plantilla.format(org=organization_id or _SIN_ORGANIZACION)


def _leer_json_de_ajuste(db: Session, clave: str, respaldo: str | None = None):
    """El JSON de ese ajuste, con respaldo en otra clave si no existe.

    Devuelve `None` cuando no hay nada legible, para que quien llama distinga
    «no hay fila» de «hay fila con un valor vacio».
    """
    from app.models.settings import AppSetting

    for k in (clave, respaldo):
        if not k:
            continue
        try:
            fila = db.query(AppSetting).filter(AppSetting.key == k).first()
            if fila and fila.value:
                return json.loads(fila.value)
        except Exception:
            _logger.debug(
                "no se pudo leer el ajuste %s; se prueba el respaldo", k, exc_info=True)
    return None


def _escribir_json_de_ajuste(db: Session, clave: str, valor, descripcion: str = "") -> None:
    from app.models.settings import AppSetting

    serializado = json.dumps(valor)
    fila = db.query(AppSetting).filter(AppSetting.key == clave).first()
    if fila:
        fila.value = serializado
    else:
        db.add(AppSetting(key=clave, value=serializado, description=descripcion))
    db.flush()


def estado_del_trabajo(db: Session, organization_id: str | None = None) -> dict:
    """El estado de la ultima ejecucion del trabajo de esa organizacion."""
    datos = _leer_json_de_ajuste(
        db, _clave_por_organizacion(
            JOB_RUNTIME_KEY_TEMPLATE, organization_id, JOB_RUNTIME_KEY_LEGACY))
    if not isinstance(datos, dict):
        return {
            "running": False,
            "status": "never_run",
            "last_job_id": None,
            "started_at": None,
            "completed_at": None,
            "duration_ms": None,
            "stats": None,
            "error": None,
        }
    return datos


def guardar_estado_del_trabajo(
    db: Session, estado: dict, organization_id: str | None = None,
) -> None:
    _escribir_json_de_ajuste(
        db, _clave_por_organizacion(
            JOB_RUNTIME_KEY_TEMPLATE, organization_id, JOB_RUNTIME_KEY_LEGACY),
        estado, "Auto-resolution job runtime state")


def historial_del_trabajo(db: Session, organization_id: str | None = None) -> list:
    """Las ultimas ejecuciones, de la mas reciente a la mas antigua."""
    datos = _leer_json_de_ajuste(
        db, _clave_por_organizacion(
            JOB_HISTORY_KEY_TEMPLATE, organization_id, JOB_HISTORY_KEY_LEGACY))
    return datos if isinstance(datos, list) else []


def anotar_en_el_historial(
    db: Session, registro: dict, organization_id: str | None = None,
) -> None:
    """Añade una ejecucion al principio y recorta al tope."""
    clave = _clave_por_organizacion(
        JOB_HISTORY_KEY_TEMPLATE, organization_id, JOB_HISTORY_KEY_LEGACY)
    historial = historial_del_trabajo(db, organization_id)
    historial = [registro] + historial
    _escribir_json_de_ajuste(
        db, clave, historial[:MAX_HISTORIAL_DEL_TRABAJO],
        "Auto-resolution job history")


def _feedback_key_for(ticket: "Ticket") -> str:
    """Construye la clave AppSetting de feedback_stats por organización.
    Antes era una sola clave global → stats de orgs distintas se mezclaban
    y el composite_confidence usaba historical rate cross-tenant.
    """
    org_id = getattr(ticket, "organization_id", None) or "global"
    return FEEDBACK_SETTING_KEY_TEMPLATE.format(org=org_id)

DEFAULT_AUTO_RESOLUTION_CONFIG = {
    "threshold_auto": CONFIDENCE_THRESHOLD_AUTO,
    "threshold_suggest": CONFIDENCE_THRESHOLD_SUGGEST,
    "auto_close_hours_after_resolution": AUTO_CLOSE_HOURS_AFTER_RESOLUTION,
    "validation_window_hours": VALIDATION_WINDOW_HOURS,
    "default_job_limit": 100,
}


# ── Feedback loop helpers ─────────────────────────────────────────────────────


def _clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(float(value), max_value))


def _normalize_auto_resolution_config(raw: dict | None) -> dict:
    merged = {**DEFAULT_AUTO_RESOLUTION_CONFIG, **(raw or {})}

    threshold_auto = _clamp(merged.get("threshold_auto", CONFIDENCE_THRESHOLD_AUTO), 0.0, 1.0)
    threshold_suggest = _clamp(merged.get("threshold_suggest", CONFIDENCE_THRESHOLD_SUGGEST), 0.0, 1.0)
    if threshold_suggest > threshold_auto:
        threshold_suggest = threshold_auto

    auto_close_hours = int(_clamp(merged.get("auto_close_hours_after_resolution", AUTO_CLOSE_HOURS_AFTER_RESOLUTION), 1, 720))
    validation_hours = int(_clamp(merged.get("validation_window_hours", VALIDATION_WINDOW_HOURS), 1, 720))
    default_job_limit = int(_clamp(merged.get("default_job_limit", 100), 1, 500))

    return {
        "threshold_auto": round(threshold_auto, 4),
        "threshold_suggest": round(threshold_suggest, 4),
        "auto_close_hours_after_resolution": auto_close_hours,
        "validation_window_hours": validation_hours,
        "default_job_limit": default_job_limit,
    }


def get_auto_resolution_config(db: Session, organization_id: str | None = None) -> dict:
    """La config de auto-resolucion de esa organizacion, ya normalizada.

    Auditoria 2026-08: esto usaba una sola clave sin organizacion, asi que
    **cualquier administrador cambiaba los umbrales de todos los clientes** —los
    de confianza, el auto-cierre y el tope del trabajo—. Ahora la clave lleva la
    organizacion, con respaldo en la desnuda para no perder la configuracion de
    un despliegue en marcha.
    """
    datos = _leer_json_de_ajuste(
        db,
        _clave_por_organizacion(
            AUTO_CONFIG_SETTING_KEY_TEMPLATE, organization_id, AUTO_CONFIG_SETTING_KEY),
        # La config SI hereda de la global: es el valor por defecto del
        # despliegue, y una organizacion que no ha tocado nada debe usarlo. El
        # estado del trabajo no hereda, porque el trabajo de otro no es el suyo.
        respaldo=AUTO_CONFIG_SETTING_KEY if organization_id else None,
    )
    return _normalize_auto_resolution_config(datos if isinstance(datos, dict) else None)


def save_auto_resolution_config(
    db: Session, payload: dict, organization_id: str | None = None,
) -> dict:
    """Guarda la config de esa organizacion, fusionada sobre la vigente."""
    actual = get_auto_resolution_config(db, organization_id)
    actualizada = _normalize_auto_resolution_config({**actual, **(payload or {})})
    clave = _clave_por_organizacion(
        AUTO_CONFIG_SETTING_KEY_TEMPLATE, organization_id, AUTO_CONFIG_SETTING_KEY)
    _escribir_json_de_ajuste(
        db, clave, actualizada, "Auto-resolution dynamic config")
    return actualizada

def _load_feedback_stats(db: Session, key: str = FEEDBACK_SETTING_KEY) -> dict:
    """Load per-category/priority feedback counters from AppSetting."""
    try:
        from app.models.settings import AppSetting
        row = db.query(AppSetting).filter(AppSetting.key == key).first()
        if row and row.value:
            return json.loads(row.value)
    # intentional: best-effort fallback, log noise outweighs diagnostic value
    except Exception:
        _logger.debug("_load_feedback_stats: fallo best-effort ignorado", exc_info=True)
    return {}


def _save_feedback_stats(db: Session, stats: dict, key: str = FEEDBACK_SETTING_KEY) -> None:
    """Persist feedback counters to AppSetting."""
    try:
        from app.models.settings import AppSetting
        row = db.query(AppSetting).filter(AppSetting.key == key).first()
        if row:
            row.value = json.dumps(stats)
        else:
            db.add(AppSetting(key=key, value=json.dumps(stats)))
        db.flush()
    except Exception as exc:
        _logger.debug("Could not save feedback stats: %s", exc)


def _bucket_key(ticket: Ticket) -> str:
    """Return a stable bucket key for feedback tracking."""
    category = getattr(ticket, "category", None) or "unknown"
    priority = str(getattr(ticket, "priority", "p3_medium"))
    return f"{category}::{priority}"


def _get_historical_success_rate(db: Session, ticket: Ticket) -> float:
    """Return historical auto-resolution success rate (0-100) for this ticket's bucket.

    Stats segmentadas por organización (multi-tenant). Antes era una sola
    clave AppSetting global → bucket cross-tenant mezclado.
    """
    stats = _load_feedback_stats(db, _feedback_key_for(ticket))
    key = _bucket_key(ticket)
    bucket = stats.get(key, {})
    total = bucket.get("total", 0)
    success = bucket.get("success", 0)
    if total >= 5:
        return (success / total) * 100.0
    return 50.0  # neutral default when insufficient data


def _composite_confidence(ai_confidence: float, db: Session, ticket: Ticket) -> float:
    """Compute composite confidence combining AI score, KB similarity, and historical rate.

    Weights:
      - AI confidence (LLM):   50%
      - KB similarity score:   30%
      - Historical success:    20%

    Returns a value in [0, 1].
    """
    ai_score = ai_confidence * 100.0

    # KB similarity component from incident_intelligence_service
    kb_score = 0.0
    try:
        from app.services.service_desk.incident_intelligence_service import (
            _get_top_kb_similarity,
        )
        query_text = f"{ticket.title or ''}\n{ticket.description or ''}".strip()
        kb_sim, _ = _get_top_kb_similarity(db, query_text)
        kb_score = kb_sim * 100.0
    except Exception:
        _logger.debug("_composite_confidence: excepcion ignorada", exc_info=True)
        kb_score = ai_score  # fallback: use AI score

    historical_rate = _get_historical_success_rate(db, ticket)

    composite = (
        ai_score * 0.50
        + kb_score * 0.30
        + historical_rate * 0.20
    )
    return min(composite / 100.0, 1.0)


def record_resolution_feedback(
    db: Session,
    ticket: Ticket,
    success: bool,
) -> None:
    """Record whether an auto-resolution was successful (not reopened) or failed.

    Updates the per-bucket counter in AppSetting for future scoring.
    Stats segmentadas por organización del ticket.
    """
    fb_key = _feedback_key_for(ticket)
    stats = _load_feedback_stats(db, fb_key)
    key = _bucket_key(ticket)
    bucket = stats.setdefault(key, {"total": 0, "success": 0, "failed": 0})
    bucket["total"] += 1
    if success:
        bucket["success"] += 1
    else:
        bucket["failed"] += 1
    _save_feedback_stats(db, stats, fb_key)
    _logger.info(
        "Recorded auto-resolution feedback for bucket '%s': success=%s (total=%d, success=%d)",
        key, success, bucket["total"], bucket["success"],
    )


def validate_auto_resolution(db: Session, ticket: Ticket) -> dict:
    """Check if an auto-resolved ticket was later reopened (resolution failed).

    Should be called N hours after auto-resolution (e.g. via scheduled job).
    Updates feedback stats and marks the ticket if re-opened.

    Returns: {validated: bool, reopened: bool, ticket_id, ticket_number}
    """
    if not ticket.auto_resolved:
        return {"validated": False, "reopened": False, "ticket_id": ticket.id, "ticket_number": ticket.number}

    # A "reopened" resolution means the ticket is no longer in resolved/closed state
    # after having been auto-resolved
    is_reopened = ticket.status not in [TicketStatus.resolved, TicketStatus.closed]

    record_resolution_feedback(db, ticket, success=not is_reopened)

    if is_reopened:
        _logger.warning(
            "Auto-resolved ticket %s was reopened — recording as failed resolution",
            ticket.number,
        )
        try:
            from app.models.service_desk import TicketHistory
            db.add(TicketHistory(
                ticket_id=ticket.id,
                field_name="auto_resolution_validation",
                old_value="resolved",
                new_value="reopened_after_auto_resolve",
                changed_by_user_id=None,
            ))
            db.flush()
        # intentional: best-effort fallback, log noise outweighs diagnostic value
        except Exception:
            _logger.debug("validate_auto_resolution: fallo best-effort ignorado", exc_info=True)

    return {
        "validated": True,
        "reopened": is_reopened,
        "ticket_id": ticket.id,
        "ticket_number": ticket.number,
    }


def get_auto_resolution_stats(db: Session) -> dict:
    """Return aggregate auto-resolution stats: overall + per-bucket success rates."""
    from sqlalchemy import func as sqlfunc

    total_auto = (
        db.query(sqlfunc.count(Ticket.id))
        .filter(Ticket.auto_resolved == True)
        .scalar()
    ) or 0

    total_tickets = (
        db.query(sqlfunc.count(Ticket.id))
        .scalar()
    ) or 1

    feedback = _load_feedback_stats(db)
    overall_success = 0
    overall_total = 0
    per_bucket = []
    for key, bucket in feedback.items():
        t = bucket.get("total", 0)
        s = bucket.get("success", 0)
        overall_total += t
        overall_success += s
        per_bucket.append({
            "bucket": key,
            "total": t,
            "success": s,
            "failed": bucket.get("failed", 0),
            "success_rate": round((s / t) * 100, 1) if t > 0 else None,
        })

    per_bucket.sort(key=lambda x: x["total"], reverse=True)

    return {
        "total_auto_resolved": total_auto,
        "pct_of_all_tickets": round((total_auto / total_tickets) * 100, 2),
        "feedback_total_validated": overall_total,
        "overall_success_rate": round((overall_success / overall_total) * 100, 1) if overall_total > 0 else None,
        "per_bucket": per_bucket,
    }


def run_auto_close_job(db: Session, organization_id: str | None = None) -> dict:
    """Auto-close tickets that were auto-resolved and have had no reopening
    within AUTO_CLOSE_HOURS_AFTER_RESOLUTION hours.

    Also triggers post-resolution validation for eligible tickets.

    Con `organization_id` solo cierra tickets de esa organizacion, y usa SU
    configuracion de horas. Sin el recorre todo, que es lo que quiere un cron
    global — pero no lo que quiere un administrador de un cliente pulsando un
    boton, y eso es lo que hacia el endpoint. Auditoria 2026-08.

    Returns: {processed, auto_closed, validated, failed}
    """
    stats = {"processed": 0, "auto_closed": 0, "validated": 0, "failed": 0}
    cfg = get_auto_resolution_config(db, organization_id)
    auto_close_hours = int(cfg["auto_close_hours_after_resolution"])
    validation_hours = int(cfg["validation_window_hours"])
    cutoff = datetime.now(timezone.utc) - timedelta(hours=auto_close_hours)
    validation_cutoff = datetime.now(timezone.utc) - timedelta(hours=validation_hours)

    try:
        # Tickets eligible for auto-close: auto_resolved, still in resolved state, resolved > cutoff ago
        consulta = db.query(Ticket).filter(
            Ticket.auto_resolved == True,
            Ticket.status == TicketStatus.resolved,
            Ticket.auto_resolved_at <= cutoff,
        )
        if organization_id:
            consulta = consulta.filter(Ticket.organization_id == organization_id)
        candidates = consulta.all()

        for ticket in candidates:
            try:
                ticket.status = TicketStatus.closed
                ticket.closed_at = datetime.now(timezone.utc)
                record_resolution_feedback(db, ticket, success=True)
                stats["auto_closed"] += 1
                stats["processed"] += 1
                db.commit()
            except Exception as exc:
                _logger.error("auto_close failed for %s: %s", ticket.number, exc)
                stats["failed"] += 1
                db.rollback()

        # Validate tickets resolved within the validation window (48h) that need feedback
        validation_candidates = (
            db.query(Ticket)
            .filter(
                Ticket.auto_resolved == True,
                Ticket.auto_resolved_at >= validation_cutoff,
                Ticket.auto_resolved_at <= cutoff,  # not yet in auto-close window
            )
            .all()
        )

        for ticket in validation_candidates:
            try:
                validate_auto_resolution(db, ticket)
                stats["validated"] += 1
                db.commit()
            except Exception as exc:
                _logger.error("validate failed for %s: %s", ticket.number, exc)
                db.rollback()

    except Exception as exc:
        _logger.error("run_auto_close_job failed: %s", exc)

    return stats


def analyze_ticket_for_resolution(
    db: Session, ticket: Ticket, current_user=None
) -> dict:
    """
    Analyze a ticket and suggest possible resolutions.

    Returns: {
        "ticket_id": str,
        "analysis": str (reasoning),
        "suggestion": str (proposed resolution),
        "confidence": float (0-1),
        "kb_sources": list[dict] (matched KB articles),
        "action_taken": str ("auto-resolved" | "suggested" | "none"),
        "recommendation": str,
    }
    """
    result = {
        "ticket_id": ticket.id,
        "analysis": "",
        "suggestion": "",
        "confidence": 0.0,
        "ai_raw_confidence": 0.0,
        "kb_sources": [],
        "action_taken": "none",
        "recommendation": "",
    }

    if not ticket.description:
        result["recommendation"] = "Ticket sin descripción, no se puede analizar"
        return result

    try:
        # ── Step 1: Search KB for similar articles ──────────────────────────
        kb_articles = _search_kb(db, ticket)
        result["kb_sources"] = [
            {
                "id": a.id,
                "title": a.title,
                "number": a.number,
                "status": a.status,
                "helpful_count": a.helpful_count,
            }
            for a in kb_articles[:3]  # Top 3
        ]

        # ── Step 2: Build context for AI analysis ──────────────────────────
        kb_text = ""
        if kb_articles:
            kb_text = "\n\n=== KNOWLEDGE BASE SOURCES ===\n"
            for article in kb_articles[:3]:
                kb_text += f"\n[{article.number}] {article.title}\n"
                kb_text += f"Body: {article.body[:500]}\n"

        # ── Step 3: Call AI to analyze ticket ──────────────────────────────
        system_prompt = """You are an AI expert in IT Service Desk.

        Analyze the following support ticket and:
        1. Understand the problem
        2. Search the KB knowledge provided
        3. Suggest a resolution with confidence level (0-100)
        4. Format your response as JSON with: {
            "analysis": "explanation of the problem",
            "suggestion": "step-by-step resolution or workaround",
            "confidence": 85,
            "root_cause": "brief root cause"
        }

        Respond ONLY with valid JSON, no markdown."""

        ticket_content = f"""
        Ticket #{ticket.number}
        Priority: {ticket.priority}
        Type: {ticket.ticket_type}
        Title: {ticket.title}
        Description: {ticket.description}
        Status: {ticket.status}
        {kb_text}
        """

        ai_response = call_ai(
            db,
            messages=[{"role": "user", "content": ticket_content}],
            system=system_prompt,
            module="auto_resolution",
            user_id=current_user.id if current_user else None,
            model=None,
            max_tokens=500,
            # Pasar contexto org evita que el dispatcher no encuentre
            # provider scoped por organización.
            is_superadmin=bool(getattr(current_user, "is_superadmin", False)) if current_user else True,
            organization_id=getattr(current_user, "organization_id", None) if current_user else None,
        )

        # ── Step 4: Parse AI response ──────────────────────────────────────
        try:
            ai_json = json.loads(ai_response)
            result["analysis"] = ai_json.get("analysis", "")
            result["suggestion"] = ai_json.get("suggestion", "")
            ai_raw_confidence = ai_json.get("confidence", 0) / 100.0
            root_cause = ai_json.get("root_cause", "")
        except (json.JSONDecodeError, ValueError):
            # Fallback if AI returns non-JSON
            result["analysis"] = ai_response[:200]
            result["suggestion"] = "Ver análisis IA más abajo"
            ai_raw_confidence = 0.5
            root_cause = "No determinada"

        # ── Step 5: Composite confidence (AI + KB similarity + historical) ─
        # Los umbrales son los de la organizacion del ticket. Antes se leia una
        # config global, asi que un ticket de un cliente se juzgaba con el
        # umbral que hubiera puesto otro. Auditoria 2026-08.
        cfg = get_auto_resolution_config(db, getattr(ticket, "organization_id", None))
        threshold_auto = float(cfg["threshold_auto"])
        threshold_suggest = float(cfg["threshold_suggest"])

        result["confidence"] = _composite_confidence(ai_raw_confidence, db, ticket)
        result["ai_raw_confidence"] = ai_raw_confidence
        if result["confidence"] >= threshold_auto:
            result["action_taken"] = "auto-resolved"
            result["recommendation"] = (
                f"✅ Auto-resolviendo con confianza {result['confidence']*100:.1f}%"
            )
            _apply_auto_resolution(db, ticket, result, current_user, root_cause)

        elif result["confidence"] >= threshold_suggest:
            result["action_taken"] = "suggested"
            result["recommendation"] = (
                f"⚠️ Sugerencia con confianza {result['confidence']*100:.1f}%. "
                f"Revisión manual recomendada."
            )
            # Post an internal comment so agents see the suggestion inline
            _post_resolution_comment(db, ticket, result["suggestion"], is_auto=False)

        else:
            result["action_taken"] = "none"
            result["recommendation"] = (
                f"❌ Confianza insuficiente ({result['confidence']*100:.1f}%). "
                f"Escalada a humano."
            )

        _logger.info(
            "Ticket %s analyzed: confidence=%.2f, action=%s",
            ticket.number, result["confidence"], result["action_taken"]
        )

    except Exception as exc:
        _logger.error("Error analyzing ticket %s: %s", ticket.number, exc)
        result["recommendation"] = f"Error en análisis: {str(exc)[:100]}"

    return result


def _articulos_publicados(db: Session, ticket_org) -> list[KBArticle]:
    """Los artículos publicados y públicos **de la organización del ticket**.

    Corrección multi-tenant: antes se leían todos los `is_public=True` sin
    filtrar por organización, así que un ticket de la organización A podía usar
    como fuente un artículo de la B.
    """
    q = db.query(KBArticle).filter(
        KBArticle.status == KBStatus.published,
        KBArticle.is_public == True,  # noqa: E712
    )
    if ticket_org and hasattr(KBArticle, "organization_id"):
        q = q.filter(KBArticle.organization_id == ticket_org)
    return q.all()


def _kb_por_semejanza(ticket: Ticket, articulos: list[KBArticle]) -> list[KBArticle]:
    """Los artículos más parecidos al ticket, por coseno sobre embeddings.

    Devuelve lista vacía si el módulo de embeddings no está disponible o si
    ninguno pasa el umbral de 0,30 — quien llama cae entonces a palabras clave.
    """
    from app.services.service_desk.incident_intelligence_service import (
        _embed_text, _cosine_similarity,
    )

    consulta = _embed_text(f"{ticket.title or ''}\n{ticket.description or ''}".strip())
    puntuados = []
    for a in articulos:
        texto = f"{a.title or ''}\n{a.summary or ''}\n{a.body or ''}".strip()
        if not texto:
            continue
        semejanza = _cosine_similarity(consulta, _embed_text(texto))
        if semejanza > 0.30:
            puntuados.append((semejanza, a))
    puntuados.sort(key=lambda x: x[0], reverse=True)
    return [a for _, a in puntuados[:5]]


def _kb_por_palabras(ticket: Ticket, articulos: list[KBArticle]) -> list[KBArticle]:
    """Respaldo sin embeddings: puntuación por coincidencia de texto.

    Los pesos —título 3, cuerpo 2, etiquetas 1— dicen qué señal vale más: que el
    título entero aparezca en el ticket es mucho más fuerte que compartir una
    etiqueta.
    """
    texto = ((ticket.title or "") + " " + (ticket.description or ""))[:200].lower()
    primeras = texto.split()[:5]

    puntuados = []
    for a in articulos:
        puntos = 0
        if a.title and a.title.lower() in texto:
            puntos += 3
        if a.body and any(palabra in a.body.lower() for palabra in primeras):
            puntos += 2
        if a.tags and any(etiqueta in texto for etiqueta in (a.tags or "").split(",")):
            puntos += 1
        if puntos > 0:
            puntuados.append((puntos, a))
    puntuados.sort(key=lambda x: x[0], reverse=True)
    return [a for _, a in puntuados[:5]]


def _search_kb(db: Session, ticket: Ticket) -> list[KBArticle]:
    """Artículos de la base de conocimiento que pueden resolver este ticket.

    Primero semejanza semántica; si el módulo no está o no encuentra nada, se
    cae a puntuación por palabras clave.
    """
    articulos = _articulos_publicados(db, getattr(ticket, "organization_id", None))

    try:
        semanticos = _kb_por_semejanza(ticket, articulos)
        if semanticos:
            return semanticos
    except Exception:
        # A propósito: el módulo de embeddings es opcional y el respaldo por
        # palabras da un resultado utilizable. Registrar cada fallo aquí sería
        # ruido en cada ticket de una instalación sin embeddings.
        _logger.debug("_search_kb: semejanza semántica no disponible", exc_info=True)

    return _kb_por_palabras(ticket, articulos)


def _post_resolution_comment(db: Session, ticket: Ticket, suggestion: str, *, is_auto: bool) -> None:
    """Add a public comment to the ticket with the AI suggestion/resolution."""
    try:
        from app.models.service_desk import TicketComment
        prefix = "🤖 **Resolución automática por IA:**" if is_auto else "🤖 **Sugerencia de resolución por IA (revisión manual recomendada):**"
        body = f"{prefix}\n\n{suggestion}"
        # Auditoria 2026-08: `TicketComment` no tiene `is_internal`; lo que
        # tiene es `is_public`, que es lo mismo al reves. SQLAlchemy responde
        # `TypeError` a una palabra clave que no es columna, y el `except` de
        # esta funcion lo registraba y seguia: **la resolucion de la IA nunca
        # llegaba al ticket**, asi que el solicitante no la veia.
        comment = TicketComment(
            ticket_id=ticket.id,
            body=body,
            is_public=True,
            author_name="AI Auto-Resolution",
        )
        db.add(comment)
    except Exception as exc:
        _logger.debug("Could not post resolution comment: %s", exc)


def _apply_auto_resolution(
    db: Session,
    ticket: Ticket,
    analysis: dict,
    current_user,
    root_cause: str,
) -> None:
    """Apply auto-resolution to ticket."""
    ticket.status = TicketStatus.resolved
    ticket.resolution_text = analysis["suggestion"]
    ticket.root_cause = root_cause
    ticket.auto_resolved = True
    ticket.auto_resolved_at = datetime.now(timezone.utc)
    ticket.auto_resolved_by = "ai_auto_resolution"
    ticket.auto_resolved_confidence = analysis["confidence"]

    # Log KB sources
    if analysis["kb_sources"]:
        ticket.resolution_kb_articles = json.dumps(
            [s["number"] for s in analysis["kb_sources"]]
        )

    # Post a public comment so the requester sees the resolution
    _post_resolution_comment(db, ticket, analysis["suggestion"], is_auto=True)

    # ── Dos integraciones que NO existen ──────────────────────────────────
    #
    # Auditoria 2026-08. Estos dos bloques decian «if available» / «if
    # notification service is available», que se lee como una condicion de
    # ejecucion. No lo es: **ninguna de las dos funciones existe**, comprobado
    # ejecutando el import.
    #
    #   · `record_sla_event` no esta en `sla_event_service`, que tiene
    #     `pause_ticket_sla`, `resume_ticket_sla` y `list_sla_events` — nada de
    #     registrar un evento al resolver. **El evento de cierre de SLA no se
    #     ha registrado nunca** en una auto-resolucion;
    #   · `notify_watchers` no esta en `watcher_service`, que tiene
    #     `list_ticket_watchers` y `watch_ticket_command` — nada de notificar.
    #     **A los observadores de un ticket nunca se les ha avisado** de que la
    #     IA lo resolvio.
    #
    # No se implementan aqui a proposito: que evento de SLA corresponde y por
    # que canal se avisa a un observador son decisiones de producto, no huecos
    # que rellenar. Lo que si se arregla es el disfraz — el comentario decia
    # «si esta disponible» y la realidad es «no esta escrito».
    #
    # Y se separa el fallo del import del fallo de la llamada: el dia que
    # alguien las implemente, un error suyo tiene que verse y no confundirse
    # con «no disponible».
    try:
        from app.services.service_desk.sla_event_service import (  # noqa: F401
            record_sla_event,
        )
    except ImportError:
        _logger.debug("record_sla_event no implementado; no se registra el "
                      "evento de cierre de SLA del ticket %s", ticket.number)
    else:
        try:
            record_sla_event(db, ticket, event_type="resolved",
                             actor="ai_auto_resolution")
        except Exception:
            _logger.warning("record_sla_event ha fallado para el ticket %s",
                            ticket.number, exc_info=True)

    try:
        from app.services.service_desk.watcher_service import (  # noqa: F401
            notify_watchers,
        )
    except ImportError:
        _logger.debug("notify_watchers no implementado; no se avisa a los "
                      "observadores del ticket %s", ticket.number)
    else:
        try:
            notify_watchers(db, ticket, event="resolved",
                            message=analysis["suggestion"][:300])
        except Exception:
            _logger.warning("notify_watchers ha fallado para el ticket %s",
                            ticket.number, exc_info=True)

    db.flush()
    _logger.info(
        "Ticket %s auto-resolved by AI (confidence: %.2f%%)",
        ticket.number,
        analysis["confidence"] * 100,
    )


def run_daily_auto_resolution_job(db: Session, *, limit: int | None = None,
                                  organization_id: str | None = None) -> dict:
    """
    Daily job: Auto-analyze open tickets and resolve if confident.

    Multi-tenant: si ``organization_id`` es provisto, sólo procesa tickets de
    esa organización. Si es None (uso desde cron global), procesa todos.

    También sustituye la condición ``created_at <= now()`` (siempre true) por
    ``<= cutoff`` para no procesar tickets recién creados.

    Returns stats: {"processed", "auto_resolved", "suggested", "failed"}.
    """
    stats = {"processed": 0, "auto_resolved": 0, "suggested": 0, "failed": 0}

    try:
        cfg = get_auto_resolution_config(db, organization_id)
        configured_limit = int(cfg.get("default_job_limit", 100))
        safe_limit = max(1, min(int(limit if limit is not None else configured_limit), 500))
        # Solo analiza tickets con al menos 15 min de antigüedad para evitar
        # interrumpir creación + asignación humana inmediata.
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)
        q = (
            db.query(Ticket)
            .filter(
                Ticket.status.notin_(
                    [TicketStatus.resolved, TicketStatus.closed, TicketStatus.cancelled]
                ),
                Ticket.auto_resolved == False,
                Ticket.created_at <= cutoff,
            )
        )
        if organization_id:
            # Auditoria 2026-08: aqui habia un `outerjoin` a `Project` con un
            # comentario que decia «Ticket no tiene organization_id propia». Ese
            # comentario esta obsoleto: **si la tiene**, y el filtro que
            # implementaba era peor, porque su
            # `or_(project_id IS NULL, Project.organization_id == org)` dejaba
            # pasar los tickets sin proyecto a TODAS las organizaciones. Es
            # ademas la columna que usa la propia guarda de tenant de
            # `TenantSession`, asi que filtrar por otra via era incoherente.
            q = q.filter(Ticket.organization_id == organization_id)
        open_tickets = q.order_by(Ticket.created_at.desc()).limit(safe_limit).all()

        for ticket in open_tickets:
            try:
                analysis = analyze_ticket_for_resolution(db, ticket)
                stats["processed"] += 1

                if analysis["action_taken"] == "auto-resolved":
                    stats["auto_resolved"] += 1
                elif analysis["action_taken"] == "suggested":
                    stats["suggested"] += 1

                db.commit()

            except Exception as exc:
                _logger.error("Error processing ticket %s: %s", ticket.number, exc)
                stats["failed"] += 1
                db.rollback()

        _logger.info(
            "Auto-resolution job completed: processed=%d, resolved=%d, suggested=%d, failed=%d",
            stats["processed"],
            stats["auto_resolved"],
            stats["suggested"],
            stats["failed"],
        )

    except Exception as exc:
        _logger.error("Auto-resolution job failed: %s", exc)

    return stats
