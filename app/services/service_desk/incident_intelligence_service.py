"""Incident Intelligence Service — Fase 1 ITSM Enhancement.

Provides:
- Auto-resolution scoring (KB similarity + historical + urgency)
- Alert deduplication / correlation window
- SLA breach prediction (proactive at 60% time consumed)
- ML incident routing score (extends workload_service)
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.service_desk import (
    KBArticle,
    KBStatus,
    ServiceItem,
    Ticket,
    TicketHistory,
    TicketPriority,
    TicketStatus,
)
from app.services.sla_service import SLA_HOURS

logger = logging.getLogger(__name__)


def _ticket_category_value(t) -> Optional[str]:
    """FIX: ``Ticket`` no expone columna ``category`` directa. La "categoría"
    real vive en ``service_item.category_id`` (cuando hay service_item) o se
    aproxima con ``ticket_type``. Centralizamos el accessor para evitar
    AttributeError en runtime.
    """
    if t is None:
        return None
    try:
        si = getattr(t, "service_item", None)
        cat_id = getattr(si, "category_id", None) if si is not None else None
        if cat_id:
            return str(cat_id)
    # intentional: best-effort fallback, log noise outweighs diagnostic value
    except Exception:  # noqa: S110
        pass
    tt = getattr(t, "ticket_type", None)
    if tt is None:
        return None
    return str(getattr(tt, "value", tt))

# ── Constants ─────────────────────────────────────────────────────────────────

# Score threshold above which a ticket is auto-resolved via KB
AUTO_RESOLVE_CONFIDENCE_THRESHOLD = 0.85

# Percentage of SLA window consumed that triggers a proactive breach alert
SLA_BREACH_WARN_PCT = 0.60

# Time window (minutes) for alert deduplication grouping by CI + category
ALERT_DEDUP_WINDOW_MINUTES = 5

# Min identical tickets in period to flag a potential Problem
PROBLEM_DETECTION_THRESHOLD = 3
PROBLEM_DETECTION_WINDOW_HOURS = 24


# ── KB similarity helpers ─────────────────────────────────────────────────────

def _cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Cosine similarity between two vectors. Returns 0.0 on dimension mismatch."""
    if len(v1) != len(v2) or not v1:
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))  # noqa: B905
    norm1 = sum(a * a for a in v1) ** 0.5
    norm2 = sum(b * b for b in v2) ** 0.5
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


def _embed_text(text: str) -> list[float]:
    """Encode text to vector using the configured semantic backend.

    Falls back to TF-IDF character n-gram hashing when sentence-transformers
    is not available (avoids hard dependency).
    """
    try:
        from app.services.semantic_classifier import _get_model
        model, _ = _get_model()
        emb = model.encode([text], show_progress_bar=False)[0]
        return emb.tolist() if hasattr(emb, "tolist") else list(emb)
    except Exception:
        # Lightweight fallback: character 3-gram frequency vector (dim=256)
        import hashlib
        vec = [0.0] * 256
        text_lower = text.lower()
        for i in range(len(text_lower) - 2):
            gram = text_lower[i:i + 3]
            idx = int(hashlib.md5(gram.encode(), usedforsecurity=False).hexdigest()[:4], 16) % 256
            vec[idx] += 1.0
        total = sum(vec) or 1.0
        return [v / total for v in vec]


def _get_top_kb_similarity(db: Session, query_text: str) -> tuple[float, Optional[str]]:
    """Return (best_similarity_score, kb_article_id) against published KB.

    Returns (0.0, None) when no articles exist.
    """
    articles = (
        db.query(KBArticle)
        .filter(KBArticle.status == KBStatus.published)
        .all()
    )
    if not articles:
        return 0.0, None

    q_emb = _embed_text(query_text)
    best_score = 0.0
    best_id = None

    for article in articles:
        text = f"{article.title or ''}\n{article.summary or ''}\n{article.body or ''}".strip()
        if not text:
            continue
        a_emb = _embed_text(text)
        sim = _cosine_similarity(q_emb, a_emb)
        if sim > best_score:
            best_score = sim
            best_id = article.id

    return best_score, best_id


# ── Auto-resolution scoring ───────────────────────────────────────────────────

def score_auto_resolution(db: Session, ticket: Ticket) -> dict:
    """Compute auto-resolution confidence for a ticket.

    Combines:
    - KB semantic similarity (40%)
    - Historical resolution rate for same category+priority (30%)
    - Priority-based urgency factor (30%)

    Returns a dict with keys:
      score (0-100), action ('auto_resolve' | 'suggest_kb' | 'escalate'),
      kb_article_id, kb_similarity, historical_rate, urgency_factor
    """
    query_text = f"{ticket.title or ''}\n{ticket.description or ''}".strip()
    kb_sim, kb_article_id = _get_top_kb_similarity(db, query_text)
    kb_score = kb_sim * 100.0

    # Historical resolution rate for same category + priority (closed tickets < 10 min)
    # FIX: Ticket no tiene .category; usamos service_item.category_id via JOIN
    # cuando aplica. Si el ticket no tiene service_item, caemos a un filtro
    # solo por ticket_type (fallback razonable, mismo grupo de incidencias).
    cat_value = _ticket_category_value(ticket)
    si_cat_id = getattr(getattr(ticket, "service_item", None), "category_id", None)

    def _filter_by_category(q):
        if si_cat_id:
            return q.join(ServiceItem, Ticket.service_item_id == ServiceItem.id).filter(
                ServiceItem.category_id == si_cat_id
            )
        if cat_value and getattr(ticket, "ticket_type", None) is not None:
            return q.filter(Ticket.ticket_type == ticket.ticket_type)
        return q

    base_q = db.query(func.count(Ticket.id)).filter(
        Ticket.priority == ticket.priority,
        Ticket.status == TicketStatus.closed,
    )
    total_similar = (_filter_by_category(base_q).scalar()) or 0

    if total_similar > 0:
        fast_q = db.query(func.count(Ticket.id)).filter(
            Ticket.priority == ticket.priority,
            Ticket.status == TicketStatus.closed,
            Ticket.first_response_minutes <= 10,
        )
        fast_closed = (_filter_by_category(fast_q).scalar()) or 0
        historical_rate = (fast_closed / total_similar) * 100.0
    else:
        historical_rate = 40.0  # neutral default

    # Priority urgency: P1 should rarely auto-resolve without human review
    urgency_factors = {
        TicketPriority.p1_critical: 20.0,
        TicketPriority.p2_high:     60.0,
        TicketPriority.p3_medium:   80.0,
        TicketPriority.p4_low:      95.0,
    }
    urgency_factor = urgency_factors.get(ticket.priority, 50.0)

    score = (
        kb_score * 0.40
        + historical_rate * 0.30
        + urgency_factor * 0.30
    )

    if score >= AUTO_RESOLVE_CONFIDENCE_THRESHOLD * 100 and kb_article_id:
        action = "auto_resolve"
    elif kb_article_id and kb_sim > 0.50:
        action = "suggest_kb"
    else:
        action = "escalate"

    return {
        "score": round(score, 2),
        "action": action,
        "kb_article_id": kb_article_id,
        "kb_similarity": round(kb_sim, 4),
        "historical_rate": round(historical_rate, 2),
        "urgency_factor": urgency_factor,
    }


def auto_resolve_ticket(
    db: Session,
    ticket: Ticket,
    kb_article_id: str,
    resolved_by_user_id: Optional[str] = None,
) -> bool:
    """Mark a ticket as resolved via KB auto-resolution.

    Logs to TicketHistory and returns True on success.
    """
    article = db.query(KBArticle).filter(KBArticle.id == kb_article_id).first()
    if not article:
        logger.warning("auto_resolve_ticket: KB article %s not found", kb_article_id)
        return False

    old_status = ticket.status
    ticket.status = TicketStatus.resolved
    ticket.resolution = (
        f"[Auto-resolved] Resolved automatically via KB article: "
        f"{article.number} — {article.title}"
    )
    ticket.resolved_at = datetime.now(timezone.utc)

    db.add(TicketHistory(
        ticket_id=ticket.id,
        field_name="status",
        old_value=str(old_status),
        new_value=TicketStatus.resolved,
        changed_by_user_id=resolved_by_user_id,
    ))
    db.add(TicketHistory(
        ticket_id=ticket.id,
        field_name="resolution",
        old_value="",
        new_value=ticket.resolution[:500],
        changed_by_user_id=resolved_by_user_id,
    ))

    logger.info(
        "Ticket %s auto-resolved via KB article %s (confidence threshold met)",
        ticket.number,
        article.number,
    )
    return True


# ── Alert deduplication ───────────────────────────────────────────────────────

def find_duplicate_alert(db: Session, ticket: Ticket) -> Optional[Ticket]:
    """Find an existing open ticket that is likely a duplicate of *ticket*.

    Criteria (all must match):
    - Same category
    - Same priority
    - Same CI (if set)
    - Created within ALERT_DEDUP_WINDOW_MINUTES of each other
    - Not the same ticket id
    - Status not resolved/closed/cancelled
    """
    # FIX: usamos helper en lugar de ticket.category (no existe en el modelo).
    cat_value = _ticket_category_value(ticket)
    if not cat_value:
        return None

    window_start = (ticket.created_at or datetime.now(timezone.utc)) - timedelta(
        minutes=ALERT_DEDUP_WINDOW_MINUTES
    )

    q = (
        db.query(Ticket)
        .filter(
            Ticket.id != ticket.id,
            Ticket.priority == ticket.priority,
            Ticket.status.not_in(
                [TicketStatus.resolved, TicketStatus.closed, TicketStatus.cancelled]
            ),
            Ticket.created_at >= window_start,
        )
    )

    # FIX: filtrar por categoría vía service_item.category_id (si aplica) o
    # ticket_type como fallback.
    si_cat_id = getattr(getattr(ticket, "service_item", None), "category_id", None)
    if si_cat_id:
        q = q.join(ServiceItem, Ticket.service_item_id == ServiceItem.id).filter(
            ServiceItem.category_id == si_cat_id
        )
    elif getattr(ticket, "ticket_type", None) is not None:
        q = q.filter(Ticket.ticket_type == ticket.ticket_type)

    if ticket.ci_id:
        q = q.filter(Ticket.ci_id == ticket.ci_id)

    return q.order_by(Ticket.created_at.asc()).first()


def deduplicate_new_ticket(
    db: Session,
    ticket: Ticket,
    acting_user_id: Optional[str] = None,
) -> dict:
    """Check if *ticket* is a duplicate and, if so, link it to the parent.

    Returns dict: {is_duplicate, parent_ticket_id, parent_number}
    Does NOT commit — caller must commit.
    """
    parent = find_duplicate_alert(db, ticket)
    if not parent:
        return {"is_duplicate": False, "parent_ticket_id": None, "parent_number": None}

    # Link via TicketLink (relates_to) if model available
    try:
        from app.models.service_desk import TicketLink, TicketLinkType
        existing_link = (
            db.query(TicketLink)
            .filter(
                TicketLink.source_ticket_id == ticket.id,
                TicketLink.target_ticket_id == parent.id,
            )
            .first()
        )
        if not existing_link:
            db.add(TicketLink(
                source_ticket_id=ticket.id,
                target_ticket_id=parent.id,
                link_type=TicketLinkType.duplicates,
                created_by_user_id=acting_user_id,
            ))
    except Exception as exc:
        logger.debug("Could not create TicketLink for dedup: %s", exc)

    db.add(TicketHistory(
        ticket_id=ticket.id,
        field_name="deduplication",
        old_value="",
        new_value=f"Possible duplicate of {parent.number}",
        changed_by_user_id=acting_user_id,
    ))

    logger.info(
        "Ticket %s flagged as possible duplicate of %s",
        ticket.number,
        parent.number,
    )
    return {
        "is_duplicate": True,
        "parent_ticket_id": parent.id,
        "parent_number": parent.number,
    }


# ── SLA Breach Prediction ─────────────────────────────────────────────────────

def _sla_pct_consumed(ticket: Ticket) -> Optional[float]:
    """Return the fraction (0-1) of SLA resolution window already consumed.

    Returns None when there is no resolution due date or the ticket is terminal.
    """
    if ticket.status in [TicketStatus.resolved, TicketStatus.closed, TicketStatus.cancelled]:
        return None
    if not ticket.sla_resolution_due:
        return None

    created = ticket.created_at
    if created is None:
        return None

    now = datetime.now(timezone.utc)
    due = ticket.sla_resolution_due
    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)

    total_seconds = (due - created).total_seconds()
    if total_seconds <= 0:
        return 1.0  # already past due

    elapsed = (now - created).total_seconds()
    return min(elapsed / total_seconds, 1.0)


def predict_sla_at_risk_tickets(db: Session) -> list[dict]:
    """Return all open tickets that have consumed >= SLA_BREACH_WARN_PCT of their window.

    Only returns tickets whose current `sla_resolution_status` is not already
    'breached' (those are handled by the escalation engine).
    """
    active_statuses = [
        TicketStatus.new,
        TicketStatus.assigned,
        TicketStatus.in_progress,
        TicketStatus.pending_client,
        TicketStatus.pending_third,
    ]

    tickets = (
        db.query(Ticket)
        .filter(
            Ticket.status.in_(active_statuses),
            Ticket.sla_resolution_due.isnot(None),
        )
        .all()
    )

    at_risk = []
    for ticket in tickets:
        pct = _sla_pct_consumed(ticket)
        if pct is None:
            continue
        if pct >= SLA_BREACH_WARN_PCT and ticket.sla_resolution_status != "breached":
            _resp_h, _res_h = SLA_HOURS.get(str(ticket.priority), (8, 24))
            at_risk.append({
                "ticket_id": ticket.id,
                "ticket_number": ticket.number,
                "title": ticket.title,
                "priority": str(ticket.priority),
                "pct_consumed": round(pct * 100, 1),
                "sla_resolution_due": (
                    ticket.sla_resolution_due.isoformat()
                    if ticket.sla_resolution_due
                    else None
                ),
                "assigned_to_user_id": ticket.assigned_to_user_id,
                "assigned_group_id": ticket.assigned_group_id,
            })

    at_risk.sort(key=lambda x: x["pct_consumed"], reverse=True)
    return at_risk


# ── Problem auto-detection ─────────────────────────────────────────────────────

def detect_recurring_incidents(db: Session) -> list[dict]:
    """Identify category+priority combinations with >= PROBLEM_DETECTION_THRESHOLD
    open tickets created in the last PROBLEM_DETECTION_WINDOW_HOURS hours.

    These groups are candidates for Problem creation. Does NOT auto-create problems
    — returns data for the `problem_auto_detect_task` Celery task to act on.
    """
    since = datetime.now(timezone.utc) - timedelta(hours=PROBLEM_DETECTION_WINDOW_HOURS)

    rows = (
        db.query(
            Ticket.category,
            Ticket.priority,
            func.count(Ticket.id).label("cnt"),
        )
        .filter(
            Ticket.ticket_type == "incident",
            Ticket.created_at >= since,
            Ticket.status.not_in(
                [TicketStatus.resolved, TicketStatus.closed, TicketStatus.cancelled]
            ),
            Ticket.problem_id.is_(None),  # not already linked to a problem
        )
        .group_by(Ticket.category, Ticket.priority)
        .having(func.count(Ticket.id) >= PROBLEM_DETECTION_THRESHOLD)
        .all()
    )

    result = []
    for row in rows:
        ticket_ids = [
            t.id
            for t in db.query(Ticket.id)
            .filter(
                Ticket.category == row.category,
                Ticket.priority == row.priority,
                Ticket.ticket_type == "incident",
                Ticket.created_at >= since,
                Ticket.status.not_in(
                    [TicketStatus.resolved, TicketStatus.closed, TicketStatus.cancelled]
                ),
                Ticket.problem_id.is_(None),
            )
            .all()
        ]
        result.append({
            "category": row.category,
            "priority": str(row.priority),
            "ticket_count": row.cnt,
            "ticket_ids": ticket_ids,
        })

    return result
