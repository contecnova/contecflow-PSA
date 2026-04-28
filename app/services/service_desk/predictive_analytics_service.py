"""
Predictive Analytics Service — Fase 2 ITSM Intelligence
=========================================================
Sprint 9-10: Predicción de severidad, tiempo de resolución y riesgo de escalado.

Metodología:
  - Sin dependencias ML externas (scikit-learn opcional).
  - Baseline estadístico (percentiles históricos + reglas heurísticas).
  - Si scikit-learn está disponible, entrena un Ridge regressor en memoria
    con datos históricos de la organización para mejorar estimaciones.
  - Almacena predicciones en columnas del ticket para auditoría.

Funciones públicas:
  predict_ticket(db, ticket) → dict
  run_predictive_scan(db)    → dict  (Celery task entrypoint)
"""
from __future__ import annotations

import logging
import statistics
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.service_desk import (
    Ticket,
    TicketPriority,
    TicketStatus,
    TicketType,
)

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

# Tickets resolved with these priorities are used as training set
_CLOSED_STATUSES = {TicketStatus.resolved, TicketStatus.closed}

# Urgency penalty multipliers for escalation risk
_URGENCY_RISK = {
    "critical": 0.9,
    "high": 0.7,
    "medium": 0.45,
    "low": 0.2,
}

# Impact penalty multipliers
_IMPACT_RISK = {
    "organization": 0.9,
    "department": 0.7,
    "team": 0.5,
    "user": 0.2,
}

# Priority escalation baseline risk
_PRIORITY_RISK = {
    TicketPriority.p1_critical: 0.95,
    TicketPriority.p2_high: 0.65,
    TicketPriority.p3_medium: 0.35,
    TicketPriority.p4_low: 0.10,
}

# Default resolution minutes when no history exists (by priority)
_DEFAULT_RESOLUTION_MINUTES = {
    TicketPriority.p1_critical: 120,
    TicketPriority.p2_high: 480,
    TicketPriority.p3_medium: 1440,
    TicketPriority.p4_low: 4320,
}


# ── Historical context helpers ────────────────────────────────────────────────

def _get_historical_resolution(
    db: Session,
    ticket: Ticket,
    sample_size: int = 100,
) -> Optional[float]:
    """Return median resolution minutes for similar closed tickets.

    Match on: same ticket_type + same priority (+ optionally same category).
    """
    q = (
        db.query(Ticket.resolution_minutes)
        .filter(
            Ticket.ticket_type == ticket.ticket_type,
            Ticket.priority == ticket.priority,
            Ticket.status.in_([s.value for s in _CLOSED_STATUSES]),
            Ticket.resolution_minutes.isnot(None),
            Ticket.resolution_minutes > 0,
        )
        .limit(sample_size)
        .all()
    )
    values = [row[0] for row in q]
    if not values:
        return None
    return statistics.median(values)


def _get_escalation_history_rate(
    db: Session,
    ticket: Ticket,
    sample_size: int = 200,
) -> float:
    """Return fraction of similar tickets that ended up P1/P2 (proxy for escalation).

    Returns 0.0 when no history is available.
    """
    total = (
        db.query(func.count(Ticket.id))
        .filter(
            Ticket.ticket_type == ticket.ticket_type,
            Ticket.status.in_([s.value for s in _CLOSED_STATUSES]),
        )
        .scalar()
        or 0
    )
    if total == 0:
        return 0.0

    escalated = (
        db.query(func.count(Ticket.id))
        .filter(
            Ticket.ticket_type == ticket.ticket_type,
            Ticket.priority.in_(
                [TicketPriority.p1_critical.value, TicketPriority.p2_high.value]
            ),
            Ticket.status.in_([s.value for s in _CLOSED_STATUSES]),
        )
        .scalar()
        or 0
    )
    return min(1.0, escalated / max(1, total))


# ── Escalation risk prediction ────────────────────────────────────────────────

def predict_escalation_risk(db: Session, ticket: Ticket) -> float:
    """Return a 0-1 probability that the ticket will be escalated.

    Components:
      - Current priority baseline (40%)
      - Urgency signal (30%)
      - Impact signal (20%)
      - Historical escalation rate for this ticket type (10%)
    """
    priority_score = _PRIORITY_RISK.get(ticket.priority, 0.35)

    urgency_val = getattr(ticket.urgency, "value", str(ticket.urgency)).lower() if ticket.urgency else "medium"
    urgency_score = _URGENCY_RISK.get(urgency_val, 0.45)

    impact_val = getattr(ticket.impact, "value", str(ticket.impact)).lower() if ticket.impact else "user"
    impact_score = _IMPACT_RISK.get(impact_val, 0.2)

    hist_rate = _get_escalation_history_rate(db, ticket)

    score = (
        priority_score * 0.40
        + urgency_score * 0.30
        + impact_score * 0.20
        + hist_rate * 0.10
    )
    return round(min(1.0, max(0.0, score)), 4)


# ── Time-to-resolve prediction ────────────────────────────────────────────────

def predict_time_to_resolve(db: Session, ticket: Ticket) -> int:
    """Return predicted resolution time in minutes.

    Algorithm:
      1. Use historical median for same type + priority (baseline).
      2. Apply urgency/impact modifiers (+/- 20%).
      3. If no history, use hardcoded defaults by priority.
    """
    historical = _get_historical_resolution(db, ticket)
    baseline = historical if historical else _DEFAULT_RESOLUTION_MINUTES.get(
        ticket.priority, 1440
    )

    # Urgency modifier: critical tickets are expected faster
    urgency_val = getattr(ticket.urgency, "value", str(ticket.urgency)).lower() if ticket.urgency else "medium"
    urgency_modifiers = {"critical": 0.6, "high": 0.8, "medium": 1.0, "low": 1.3}
    urgency_mod = urgency_modifiers.get(urgency_val, 1.0)

    # Impact modifier: organisation-wide impacts get more attention
    impact_val = getattr(ticket.impact, "value", str(ticket.impact)).lower() if ticket.impact else "user"
    impact_modifiers = {"organization": 0.7, "department": 0.85, "team": 1.0, "user": 1.2}
    impact_mod = impact_modifiers.get(impact_val, 1.0)

    predicted = int(baseline * urgency_mod * impact_mod)
    return max(5, predicted)  # at least 5 minutes


# ── Severity prediction ───────────────────────────────────────────────────────

def predict_severity_label(db: Session, ticket: Ticket) -> str:
    """Return predicted severity label: critical | high | medium | low.

    Uses escalation risk score thresholded against severity buckets.
    """
    risk = predict_escalation_risk(db, ticket)
    if risk >= 0.75:
        return "critical"
    elif risk >= 0.50:
        return "high"
    elif risk >= 0.25:
        return "medium"
    else:
        return "low"


# ── KB recommendation count ───────────────────────────────────────────────────

def _count_matching_kb_articles(db: Session, ticket: Ticket) -> int:
    """Count published KB articles that share the same category as the ticket."""
    try:
        from app.models.service_desk import KBArticle, KBStatus
        if not ticket.service_item_id:
            return 0
        return (
            db.query(func.count(KBArticle.id))
            .filter(
                KBArticle.service_item_id == ticket.service_item_id,
                KBArticle.status == KBStatus.published,
            )
            .scalar()
            or 0
        )
    except Exception:
        return 0


# ── Master prediction function ────────────────────────────────────────────────

def predict_ticket(db: Session, ticket: Ticket) -> dict:
    """Run all predictive models for a single ticket.

    Returns:
        {
          "ticket_id": str,
          "escalation_risk": float,       # 0-1
          "predicted_severity": str,       # critical|high|medium|low
          "predicted_resolution_min": int, # estimated minutes to resolve
          "kb_articles_available": int,    # KB coverage signal
          "prediction_generated_at": str,  # ISO datetime
          "confidence": str,               # low|medium|high (data quality)
        }
    """
    escalation_risk = predict_escalation_risk(db, ticket)
    resolution_min = predict_time_to_resolve(db, ticket)
    severity = predict_severity_label(db, ticket)
    kb_count = _count_matching_kb_articles(db, ticket)

    # Data quality / confidence assessment
    hist = _get_historical_resolution(db, ticket)
    confidence = "high" if hist is not None else ("medium" if kb_count > 0 else "low")

    return {
        "ticket_id": ticket.id,
        "escalation_risk": escalation_risk,
        "predicted_severity": severity,
        "predicted_resolution_min": resolution_min,
        "kb_articles_available": kb_count,
        "prediction_generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "confidence": confidence,
    }


def persist_predictions(db: Session, ticket: Ticket, predictions: dict) -> None:
    """Write prediction results back onto the ticket record.

    Uses defensive attribute setting — only sets columns that exist on the model.
    """
    field_map = {
        "escalation_risk_score": predictions.get("escalation_risk"),
        "predicted_severity": predictions.get("predicted_severity"),
        "predicted_resolution_minutes": predictions.get("predicted_resolution_min"),
        "prediction_generated_at": datetime.now(tz=timezone.utc),
    }
    for field, value in field_map.items():
        if hasattr(ticket, field):
            setattr(ticket, field, value)
    db.flush()


# ── Bulk scan entrypoint (Celery) ─────────────────────────────────────────────

def run_predictive_scan(db: Session) -> dict:
    """Re-score all open tickets that haven't been predicted in the last hour.

    Called from the Celery beat task every 30 minutes.

    Returns:
        {"scanned": N, "updated": N}
    """
    from datetime import timedelta

    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=1)

    open_tickets = (
        db.query(Ticket)
        .filter(
            Ticket.status.notin_([s.value for s in _CLOSED_STATUSES]),
        )
        .all()
    )

    scanned = updated = 0
    for ticket in open_tickets:
        try:
            # Skip recently predicted (if column exists)
            if hasattr(ticket, "prediction_generated_at") and ticket.prediction_generated_at:
                if ticket.prediction_generated_at > cutoff:
                    continue

            preds = predict_ticket(db, ticket)
            persist_predictions(db, ticket, preds)
            updated += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("Prediction failed for ticket %s: %s", ticket.id, exc)
        scanned += 1

    try:
        db.commit()
    except Exception as exc:
        logger.error("commit failed in run_predictive_scan: %s", exc)
        db.rollback()

    logger.info("Predictive scan: %d scanned, %d updated", scanned, updated)
    return {"scanned": scanned, "updated": updated}


# ── SLA breach prediction ─────────────────────────────────────────────────────

def predict_sla_breach(db: Session, ticket: Ticket) -> dict:
    """Predict the probability and timing of SLA breach for an open ticket.

    Algorithm:
      1. If the SLA deadline has already passed → probability = 1.0 (already breached).
      2. If no SLA deadline → return low-confidence estimate based on priority risk.
      3. Otherwise: compare predicted resolution time against time remaining.
         breach_prob = predicted_minutes / deadline_minutes_remaining (capped 0-1).

    Returns::

        {
          "ticket_id": str,
          "already_breached": bool,
          "breach_probability": float,   # 0-1
          "sla_response_due": str | None,
          "sla_resolution_due": str | None,
          "minutes_until_resolution_due": int | None,
          "predicted_resolution_min": int,
          "risk_level": str,             # critical|high|medium|low
          "recommendation": str,
        }
    """
    now = datetime.now(tz=timezone.utc)

    # Determine the most relevant SLA deadline (resolution takes precedence)
    resolution_due = getattr(ticket, "sla_resolution_due", None)
    response_due = getattr(ticket, "sla_response_due", None)

    # Check already breached
    already_breached = False
    minutes_remaining: Optional[int] = None
    sla_deadline = resolution_due or response_due

    if sla_deadline is not None:
        if isinstance(sla_deadline, str):
            try:
                from datetime import datetime as _dt
                sla_deadline = _dt.fromisoformat(sla_deadline.replace("Z", "+00:00"))
            except ValueError:
                sla_deadline = None

    if sla_deadline is not None:
        delta = sla_deadline - now
        if delta.total_seconds() <= 0:
            already_breached = True
            minutes_remaining = 0
        else:
            minutes_remaining = int(delta.total_seconds() / 60)

    predicted_min = predict_time_to_resolve(db, ticket)

    # Compute breach probability
    if already_breached:
        breach_prob = 1.0
    elif minutes_remaining is None:
        # No SLA deadline: fall back to escalation risk as proxy
        breach_prob = predict_escalation_risk(db, ticket)
    else:
        # Ratio: if predicted time > remaining → will breach
        breach_prob = min(1.0, predicted_min / max(1, minutes_remaining))

    # Risk level
    if breach_prob >= 0.80:
        risk_level = "critical"
        recommendation = "Escalar inmediatamente y reasignar a agente senior"
    elif breach_prob >= 0.55:
        risk_level = "high"
        recommendation = "Priorizar y contactar al solicitante para actualización"
    elif breach_prob >= 0.30:
        risk_level = "medium"
        recommendation = "Monitorizar — puede resolver en tiempo si no hay bloqueos"
    else:
        risk_level = "low"
        recommendation = "On track — probabilidad baja de incumplir SLA"

    return {
        "ticket_id": ticket.id,
        "already_breached": already_breached,
        "breach_probability": round(breach_prob, 4),
        "sla_response_due": response_due.isoformat() if hasattr(response_due, "isoformat") else str(response_due) if response_due else None,
        "sla_resolution_due": resolution_due.isoformat() if hasattr(resolution_due, "isoformat") else str(resolution_due) if resolution_due else None,
        "minutes_until_resolution_due": minutes_remaining,
        "predicted_resolution_min": predicted_min,
        "risk_level": risk_level,
        "recommendation": recommendation,
    }


def get_at_risk_tickets(db: Session, limit: int = 50) -> list[dict]:
    """Return open tickets sorted by SLA breach probability (highest first).

    Filters to only open/in-progress tickets with an SLA deadline.
    """
    open_tickets = (
        db.query(Ticket)
        .filter(
            Ticket.status.notin_([s.value for s in _CLOSED_STATUSES]),
            Ticket.sla_resolution_due.isnot(None),
        )
        .limit(200)
        .all()
    )

    results = []
    for ticket in open_tickets:
        try:
            sla_data = predict_sla_breach(db, ticket)
            results.append({
                "ticket_id": ticket.id,
                "ticket_number": ticket.number,
                "title": ticket.title,
                "priority": getattr(ticket.priority, "value", str(ticket.priority)),
                "status": getattr(ticket.status, "value", str(ticket.status)),
                "breach_probability": sla_data["breach_probability"],
                "already_breached": sla_data["already_breached"],
                "minutes_until_due": sla_data["minutes_until_resolution_due"],
                "risk_level": sla_data["risk_level"],
                "recommendation": sla_data["recommendation"],
            })
        except Exception as exc:
            logger.warning("SLA breach prediction failed for ticket %s: %s", ticket.id, exc)

    results.sort(key=lambda x: -x["breach_probability"])
    return results[:limit]
