"""
AI Auto-Resolution Service — Inteligent ticket resolution using IA + KB + ML.

Capabilidades:
  - Análisis automático de tickets
  - Búsqueda en KB + reglas
  - Sugerencias de resolución con score de confianza
  - Auto-resolución si confianza > threshold
  - Audit trail completo
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.service_desk import Ticket, TicketStatus, KBArticle, KBStatus
from app.services.ai_provider_service import call_ai
from app.core.config import settings

_logger = logging.getLogger("ai_auto_resolution")

# ── Auto-resolution confidence thresholds ────────────────────────────────────
CONFIDENCE_THRESHOLD_AUTO = 0.85  # Auto-resolve if >= 85%
CONFIDENCE_THRESHOLD_SUGGEST = 0.65  # Show suggestion if >= 65%


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
        )

        # ── Step 4: Parse AI response ──────────────────────────────────────
        try:
            ai_json = json.loads(ai_response)
            result["analysis"] = ai_json.get("analysis", "")
            result["suggestion"] = ai_json.get("suggestion", "")
            result["confidence"] = ai_json.get("confidence", 0) / 100.0
            root_cause = ai_json.get("root_cause", "")
        except (json.JSONDecodeError, ValueError):
            # Fallback if AI returns non-JSON
            result["analysis"] = ai_response[:200]
            result["suggestion"] = "Ver análisis IA más abajo"
            result["confidence"] = 0.5
            root_cause = "No determinada"

        # ── Step 5: Decide action ──────────────────────────────────────────
        if result["confidence"] >= CONFIDENCE_THRESHOLD_AUTO:
            result["action_taken"] = "auto-resolved"
            result["recommendation"] = (
                f"✅ Auto-resolviendo con confianza {result['confidence']*100:.1f}%"
            )
            _apply_auto_resolution(db, ticket, result, current_user, root_cause)

        elif result["confidence"] >= CONFIDENCE_THRESHOLD_SUGGEST:
            result["action_taken"] = "suggested"
            result["recommendation"] = (
                f"⚠️ Sugerencia con confianza {result['confidence']*100:.1f}%. "
                f"Revisión manual recomendada."
            )

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
    """Search KB for articles related to ticket."""
    # Simple semantic search: match title/tags
    search_terms = (ticket.title or "") + " " + (ticket.description or "")
    search_terms = search_terms[:200].lower()

    articles = (
        db.query(KBArticle)
        .filter(
            KBArticle.status == KBStatus.published,
            KBArticle.is_public == True,
        )
        .all()
    )

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

    db.flush()
    _logger.info(
        "Ticket %s auto-resolved by AI (confidence: %.2f%%)",
        ticket.number,
        analysis["confidence"] * 100,
    )


def run_daily_auto_resolution_job(db: Session) -> dict:
    """
    Daily job: Auto-analyze open tickets and resolve if confident.
    
    Returns stats: {
        "processed": count,
        "auto_resolved": count,
        "suggested": count,
        "failed": count,
    }
    """
    stats = {"processed": 0, "auto_resolved": 0, "suggested": 0, "failed": 0}

    try:
        # Get open, non-auto-assigned tickets
        open_tickets = (
            db.query(Ticket)
            .filter(
                Ticket.status.notin_(
                    [TicketStatus.resolved, TicketStatus.closed, TicketStatus.cancelled]
                ),
                Ticket.auto_resolved == False,
                Ticket.created_at <= datetime.now(timezone.utc),  # Old enough for analysis
            )
            .order_by(Ticket.created_at.desc())
            .limit(100)  # Limit batch size
            .all()
        )

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
