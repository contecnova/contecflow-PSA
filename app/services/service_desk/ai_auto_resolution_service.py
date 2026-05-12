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
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.service_desk import Ticket, TicketStatus, KBArticle, KBStatus
from app.services.ai_provider_service import call_ai
from app.core.config import settings

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
AUTO_CONFIG_SETTING_KEY = "sd.auto_resolution.config"


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


def get_auto_resolution_config(db: Session) -> dict:
    """Return persisted auto-resolution config with defaults and normalization."""
    try:
        from app.models.settings import AppSetting  # noqa: PLC0415

        row = db.query(AppSetting).filter(AppSetting.key == AUTO_CONFIG_SETTING_KEY).first()
        if row and row.value:
            return _normalize_auto_resolution_config(json.loads(row.value))
    except Exception:
        pass
    return _normalize_auto_resolution_config(None)


def save_auto_resolution_config(db: Session, payload: dict) -> dict:
    """Persist auto-resolution config into AppSetting."""
    from app.models.settings import AppSetting  # noqa: PLC0415

    current = get_auto_resolution_config(db)
    updated = _normalize_auto_resolution_config({**current, **(payload or {})})

    row = db.query(AppSetting).filter(AppSetting.key == AUTO_CONFIG_SETTING_KEY).first()
    if row:
        row.value = json.dumps(updated)
    else:
        db.add(AppSetting(key=AUTO_CONFIG_SETTING_KEY, value=json.dumps(updated)))
    db.flush()
    return updated

def _load_feedback_stats(db: Session, key: str = FEEDBACK_SETTING_KEY) -> dict:
    """Load per-category/priority feedback counters from AppSetting."""
    try:
        from app.models.settings import AppSetting  # noqa: PLC0415
        row = db.query(AppSetting).filter(AppSetting.key == key).first()
        if row and row.value:
            return json.loads(row.value)
    except Exception:
        pass
    return {}


def _save_feedback_stats(db: Session, stats: dict, key: str = FEEDBACK_SETTING_KEY) -> None:
    """Persist feedback counters to AppSetting."""
    try:
        from app.models.settings import AppSetting  # noqa: PLC0415
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
        from app.services.service_desk.incident_intelligence_service import (  # noqa: PLC0415
            _get_top_kb_similarity,
        )
        query_text = f"{ticket.title or ''}\n{ticket.description or ''}".strip()
        kb_sim, _ = _get_top_kb_similarity(db, query_text)
        kb_score = kb_sim * 100.0
    except Exception:
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
            from app.models.service_desk import TicketHistory  # noqa: PLC0415
            db.add(TicketHistory(
                ticket_id=ticket.id,
                field_name="auto_resolution_validation",
                old_value="resolved",
                new_value="reopened_after_auto_resolve",
                changed_by_user_id=None,
            ))
            db.flush()
        except Exception:
            pass

    return {
        "validated": True,
        "reopened": is_reopened,
        "ticket_id": ticket.id,
        "ticket_number": ticket.number,
    }


def get_auto_resolution_stats(db: Session) -> dict:
    """Return aggregate auto-resolution stats: overall + per-bucket success rates."""
    from sqlalchemy import func as sqlfunc  # noqa: PLC0415

    total_auto = (
        db.query(sqlfunc.count(Ticket.id))
        .filter(Ticket.auto_resolved == True)  # noqa: E712
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


def run_auto_close_job(db: Session) -> dict:
    """Auto-close tickets that were auto-resolved and have had no reopening
    within AUTO_CLOSE_HOURS_AFTER_RESOLUTION hours.

    Also triggers post-resolution validation for eligible tickets.

    Returns: {processed, auto_closed, validated, failed}
    """
    stats = {"processed": 0, "auto_closed": 0, "validated": 0, "failed": 0}
    cfg = get_auto_resolution_config(db)
    auto_close_hours = int(cfg["auto_close_hours_after_resolution"])
    validation_hours = int(cfg["validation_window_hours"])
    cutoff = datetime.now(timezone.utc) - timedelta(hours=auto_close_hours)
    validation_cutoff = datetime.now(timezone.utc) - timedelta(hours=validation_hours)

    try:
        # Tickets eligible for auto-close: auto_resolved, still in resolved state, resolved > cutoff ago
        candidates = (
            db.query(Ticket)
            .filter(
                Ticket.auto_resolved == True,  # noqa: E712
                Ticket.status == TicketStatus.resolved,
                Ticket.auto_resolved_at <= cutoff,
            )
            .all()
        )

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
                Ticket.auto_resolved == True,  # noqa: E712
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
        cfg = get_auto_resolution_config(db)
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


def _search_kb(db: Session, ticket: Ticket) -> list[KBArticle]:
    """Search KB using cosine similarity via incident_intelligence_service when available,
    falling back to keyword scoring for simpler environments.

    Multi-tenant fix: limita los artículos KB a la organización del ticket.
    Antes este search leía todos los `is_public=True` sin filtrar org,
    permitiendo que un ticket de la org A usara KB de la org B como source.
    """
    ticket_org = getattr(ticket, "organization_id", None)

    def _scope_kb(q):
        if ticket_org and hasattr(KBArticle, "organization_id"):
            return q.filter(KBArticle.organization_id == ticket_org)
        return q

    # Try semantic cosine similarity first
    try:
        from app.services.service_desk.incident_intelligence_service import (  # noqa: PLC0415
            _embed_text, _cosine_similarity,
        )
        query_text = f"{ticket.title or ''}\n{ticket.description or ''}".strip()
        q_emb = _embed_text(query_text)

        articles = _scope_kb(
            db.query(KBArticle)
            .filter(
                KBArticle.status == KBStatus.published,
                KBArticle.is_public == True,  # noqa: E712
            )
        ).all()
        scored = []
        for a in articles:
            text = f"{a.title or ''}\n{a.summary or ''}\n{a.body or ''}".strip()
            if not text:
                continue
            sim = _cosine_similarity(q_emb, _embed_text(text))
            if sim > 0.30:
                scored.append((sim, a))
        scored.sort(key=lambda x: x[0], reverse=True)
        if scored:
            return [a for _, a in scored[:5]]
    except Exception:
        pass

    # Keyword fallback
    search_terms = (ticket.title or "") + " " + (ticket.description or "")
    search_terms = search_terms[:200].lower()

    articles = _scope_kb(
        db.query(KBArticle)
        .filter(
            KBArticle.status == KBStatus.published,
            KBArticle.is_public == True,  # noqa: E712
        )
    ).all()

    # Score each article
    scored = []
    for a in articles:
        score = 0
        if a.title and a.title.lower() in search_terms:
            score += 3
        if a.body and any(word in a.body.lower() for word in search_terms.split()[:5]):
            score += 2
        if a.tags and any(tag in search_terms for tag in (a.tags or "").split(",")):
            score += 1
        if score > 0:
            scored.append((score, a))

    # Sort by score desc
    scored.sort(key=lambda x: x[0], reverse=True)
    return [a for _, a in scored[:5]]


def _post_resolution_comment(db: Session, ticket: Ticket, suggestion: str, *, is_auto: bool) -> None:
    """Add a public comment to the ticket with the AI suggestion/resolution."""
    try:
        from app.models.service_desk import TicketComment  # noqa: PLC0415
        prefix = "🤖 **Resolución automática por IA:**" if is_auto else "🤖 **Sugerencia de resolución por IA (revisión manual recomendada):**"
        body = f"{prefix}\n\n{suggestion}"
        comment = TicketComment(
            ticket_id=ticket.id,
            body=body,
            is_internal=False,
            author_name="AI Auto-Resolution",
        )
        db.add(comment)
    except Exception as exc:  # noqa: BLE001
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

    # Trigger SLA close event if available
    try:
        from app.services.service_desk.sla_event_service import record_sla_event  # noqa: PLC0415
        record_sla_event(db, ticket, event_type="resolved", actor="ai_auto_resolution")
    except Exception:
        pass

    # Notify watchers if notification service is available
    try:
        from app.services.service_desk.watcher_service import notify_watchers  # noqa: PLC0415
        notify_watchers(db, ticket, event="resolved", message=analysis["suggestion"][:300])
    except Exception:
        pass

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
        cfg = get_auto_resolution_config(db)
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
