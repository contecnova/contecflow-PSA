"""ITSM-P07 — Data-driven Routing Service (heuristic + histórico)

**Sobre el nombre "ML"** (item #61): este módulo se llama históricamente
"ML routing" pero en realidad es **scoring rule-based con features
históricas** (avg resolution time, CSAT) — NO entrena ni infiere un modelo.
Mantenemos el nombre por compatibilidad de imports; cualquier
funcionalidad ML real (predicción supervisada del mejor agente) iría en un
módulo aparte llamado, por ejemplo, ``ml_routing_classifier.py``.

Replaces the heuristic skill-keyword + load routing with a data-driven
scoring que aprovecha el histórico almacenado en ``sd_routing_feedback``.

Composite score formula (0-1):
  - Availability     30%  — respects user.status (vacation/leave → 0); load-based
  - Historical speed 35%  — resolution time vs. global avg for same bucket
  - Historical CSAT  20%  — avg CSAT from feedback for agent × bucket
  - Skill match      15%  — keyword overlap (existing logic, kept as tie-breaker)

Public API:
  get_routing_candidates(db, ticket, members) → list[AgentScore]
  predict_best_agent(db, ticket, members) → str  (user_id)
  record_routing_event(db, ticket) → None
  record_routing_outcome(db, ticket) → None
  run_outcome_scan(db) → dict
  get_routing_stats(db) → dict
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func as sqlfunc
from sqlalchemy.orm import Session

from app.models.service_desk import RoutingFeedback, Ticket, TicketStatus
from app.models.user import User, UserStatus

_logger = logging.getLogger(__name__)

# Weights must sum to 1.0
_W_AVAILABILITY = 0.30
_W_SPEED        = 0.35
_W_CSAT         = 0.20
_W_SKILL        = 0.15

_MAX_OPEN_TICKETS = 12  # capacity ceiling for availability calc
_MIN_SAMPLES      = 3   # minimum feedback rows needed to trust historical stats


# ── Availability component ────────────────────────────────────────────────────

def _availability_score(db: Session, user: User) -> float:
    """Return 0-1 availability.

    0.0  — user is on vacation or leave (unavailable)
    else — 1 - (open_ticket_count / _MAX_OPEN_TICKETS)
    """
    if user.status in (UserStatus.vacation, UserStatus.leave):
        return 0.0
    if user.status != UserStatus.active:
        return 0.1   # inactive → very low but not impossible

    open_count = (
        db.query(sqlfunc.count(Ticket.id))
        .filter(
            Ticket.assigned_to_user_id == user.id,
            Ticket.status.not_in([
                TicketStatus.resolved, TicketStatus.closed, TicketStatus.cancelled
            ]),
        )
        .scalar()
    ) or 0
    return max(0.0, (_MAX_OPEN_TICKETS - open_count) / _MAX_OPEN_TICKETS)


# ── Historical speed component ────────────────────────────────────────────────

def _avg_resolution_minutes(
    db: Session, agent_id: str, ticket_type: str | None, category_id: str | None,
    organization_id: str | None = None,
) -> float | None:
    """Return agent's average resolution_minutes for the given bucket.

    Multi-tenant: si ``organization_id`` se provee, restringe el cálculo a
    feedback de tickets de esa org. Antes leía RoutingFeedback globalmente
    → un agente de org A se beneficiaba del histórico de org B.

    Returns None if fewer than _MIN_SAMPLES feedback rows exist.
    """
    q = (
        db.query(sqlfunc.avg(RoutingFeedback.resolution_minutes))
        .filter(
            RoutingFeedback.assigned_agent_id == agent_id,
            RoutingFeedback.resolution_minutes.isnot(None),
        )
    )
    if ticket_type:
        q = q.filter(RoutingFeedback.ticket_type == ticket_type)
    if category_id:
        q = q.filter(RoutingFeedback.category_id == category_id)
    if organization_id and hasattr(RoutingFeedback, "organization_id"):
        q = q.filter(RoutingFeedback.organization_id == organization_id)

    # Only use if enough samples
    count_q = db.query(sqlfunc.count(RoutingFeedback.id)).filter(
        RoutingFeedback.assigned_agent_id == agent_id,
        RoutingFeedback.resolution_minutes.isnot(None),
    )
    if ticket_type:
        count_q = count_q.filter(RoutingFeedback.ticket_type == ticket_type)
    if organization_id and hasattr(RoutingFeedback, "organization_id"):
        count_q = count_q.filter(RoutingFeedback.organization_id == organization_id)
    count = count_q.scalar() or 0
    if count < _MIN_SAMPLES:
        return None

    avg = q.scalar()
    return float(avg) if avg is not None else None


def _global_avg_resolution_minutes(
    db: Session, ticket_type: str | None, category_id: str | None,
    organization_id: str | None = None,
) -> float:
    """Return global average resolution_minutes for the bucket (all agents).

    Multi-tenant: ``organization_id`` restringe el cálculo al tenant.
    """
    q = db.query(sqlfunc.avg(RoutingFeedback.resolution_minutes)).filter(
        RoutingFeedback.resolution_minutes.isnot(None)
    )
    if ticket_type:
        q = q.filter(RoutingFeedback.ticket_type == ticket_type)
    if category_id:
        q = q.filter(RoutingFeedback.category_id == category_id)
    if organization_id and hasattr(RoutingFeedback, "organization_id"):
        q = q.filter(RoutingFeedback.organization_id == organization_id)
    avg = q.scalar()
    # Fallback: 480 minutes (8h) if no data
    return float(avg) if avg is not None else 480.0


def _speed_score(
    db: Session, agent_id: str, ticket_type: str | None, category_id: str | None,
    organization_id: str | None = None,
) -> float:
    """Return 0-1 speed score. Higher = faster than average.

    Uses ratio: global_avg / agent_avg (capped at 1.5 to avoid extreme outliers).
    Returns neutral 0.5 when not enough data.
    """
    agent_avg = _avg_resolution_minutes(db, agent_id, ticket_type, category_id, organization_id=organization_id)
    if agent_avg is None:
        return 0.5  # no history — neutral

    global_avg = _global_avg_resolution_minutes(db, ticket_type, category_id, organization_id=organization_id)
    if agent_avg <= 0:
        return 1.0
    ratio = global_avg / agent_avg  # > 1 = faster, < 1 = slower
    return min(1.0, max(0.0, ratio / 1.5))


# ── Historical CSAT component ─────────────────────────────────────────────────

def _csat_score(
    db: Session, agent_id: str, ticket_type: str | None, category_id: str | None,
    organization_id: str | None = None,
) -> float:
    """Return 0-1 CSAT score from feedback table for this agent × bucket.

    Returns 0.6 (slightly positive neutral) when insufficient data.
    Multi-tenant: ``organization_id`` restringe el cálculo al tenant.
    """
    q = db.query(sqlfunc.avg(RoutingFeedback.csat_score)).filter(
        RoutingFeedback.assigned_agent_id == agent_id,
        RoutingFeedback.csat_score.isnot(None),
    )
    if ticket_type:
        q = q.filter(RoutingFeedback.ticket_type == ticket_type)
    if category_id:
        q = q.filter(RoutingFeedback.category_id == category_id)
    if organization_id and hasattr(RoutingFeedback, "organization_id"):
        q = q.filter(RoutingFeedback.organization_id == organization_id)

    count_q = db.query(sqlfunc.count(RoutingFeedback.id)).filter(
        RoutingFeedback.assigned_agent_id == agent_id,
        RoutingFeedback.csat_score.isnot(None),
    )
    if organization_id and hasattr(RoutingFeedback, "organization_id"):
        count_q = count_q.filter(RoutingFeedback.organization_id == organization_id)
    count = count_q.scalar() or 0
    if count < _MIN_SAMPLES:
        # Fallback: average CSAT from tickets table (also scoped if posible)
        from app.models.service_desk import Ticket as _Ticket  # noqa: PLC0415
        ticket_q = (
            db.query(sqlfunc.avg(_Ticket.csat_score))
            .filter(
                _Ticket.assigned_to_user_id == agent_id,
                _Ticket.csat_score.isnot(None),
            )
        )
        if organization_id and hasattr(_Ticket, "organization_id"):
            ticket_q = ticket_q.filter(_Ticket.organization_id == organization_id)
        avg_t = ticket_q.scalar()
        if avg_t is not None:
            return float(avg_t) / 5.0
        return 0.6

    avg = q.scalar()
    return float(avg) / 5.0 if avg is not None else 0.6


# ── Skill match component (kept from workload_service) ────────────────────────

def _skill_match(db: Session, user_id: str, category_id: str | None) -> float:
    """Keyword overlap between agent skill names and service category name."""
    if not category_id:
        return 0.5
    try:
        from app.models.service_desk import ServiceCategory  # noqa: PLC0415
        cat = db.query(ServiceCategory).filter(ServiceCategory.id == category_id).first()
        cat_name = (cat.name if cat else "") or ""
        cat_words = set(cat_name.lower().split())

        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return 0.5
        skills = getattr(user, "skills", []) or []
        if not skills:
            return 0.5

        for skill in skills:
            skill_name = (getattr(skill, "name", "") or "").lower()
            if any(w in skill_name for w in cat_words):
                return 1.0
        for skill in skills:
            skill_name = (getattr(skill, "name", "") or "").lower()
            if any(w in skill_name for w in cat_words if len(w) > 3):
                return 0.7
        return 0.3
    except Exception:
        return 0.5


# ── Composite score ───────────────────────────────────────────────────────────

def score_agent_for_ticket_ml(db: Session, user: User, ticket: Ticket) -> dict[str, Any]:
    """Compute the full ML composite score for assigning *ticket* to *user*.

    Returns a dict with component breakdown and final composite score.
    """
    def _enum_val(v: Any) -> Any:
        return v.value if hasattr(v, "value") else v

    ticket_type = str(_enum_val(ticket.ticket_type)) if ticket.ticket_type else None
    # category_id comes from service_item → category, or direct category_id if present
    category_id = None
    try:
        if ticket.service_item_id:
            from app.models.service_desk import ServiceItem  # noqa: PLC0415
            si = db.query(ServiceItem).filter(ServiceItem.id == ticket.service_item_id).first()
            if si:
                category_id = si.category_id
    # intentional: best-effort fallback, log noise outweighs diagnostic value
    except Exception:
        pass

    # Multi-tenant: aislamos el histórico por organization_id del ticket.
    org_id = getattr(ticket, "organization_id", None)
    avail   = _availability_score(db, user)
    speed   = _speed_score(db, user.id, ticket_type, category_id, organization_id=org_id)
    csat    = _csat_score(db, user.id, ticket_type, category_id, organization_id=org_id)
    skill   = _skill_match(db, user.id, category_id)

    composite = (
        avail * _W_AVAILABILITY
        + speed * _W_SPEED
        + csat  * _W_CSAT
        + skill * _W_SKILL
    )

    return {
        "user_id": user.id,
        "user_name": user.full_name if hasattr(user, "full_name") else user.username,
        "composite_score": round(composite, 4),
        "components": {
            "availability": round(avail, 4),
            "historical_speed": round(speed, 4),
            "historical_csat": round(csat, 4),
            "skill_match": round(skill, 4),
        },
        "user_status": str(user.status.value) if user.status else "unknown",
        "available": avail > 0.0,
    }


# ── Public API ────────────────────────────────────────────────────────────────

def get_routing_candidates(
    db: Session, ticket: Ticket, members: list
) -> list[dict[str, Any]]:
    """Score all members and return a ranked list (best first).

    *members* is a list of AgentGroupMember ORM objects.
    """
    results = []
    for member in members:
        user = db.query(User).filter(User.id == member.user_id).first()
        if not user:
            continue
        scored = score_agent_for_ticket_ml(db, user, ticket)
        results.append(scored)

    results.sort(key=lambda x: x["composite_score"], reverse=True)
    return results


def predict_best_agent(db: Session, ticket: Ticket, members: list) -> str | None:
    """Return the user_id of the best available agent for *ticket*.

    Prefers available agents (availability > 0). Falls back to lowest-load
    if everyone is unavailable.
    """
    candidates = get_routing_candidates(db, ticket, members)
    if not candidates:
        return None

    # Prefer available agents
    available = [c for c in candidates if c["available"]]
    if available:
        return available[0]["user_id"]

    # All unavailable — return the one with highest load score anyway
    return candidates[0]["user_id"]


def record_routing_event(db: Session, ticket: Ticket) -> None:
    """Write a RoutingFeedback row when a ticket is assigned.

    Call this after `ticket.assigned_to_user_id` is set.
    Skips gracefully if feedback already exists for this ticket.
    """
    def _enum_val(v: Any) -> Any:
        return v.value if hasattr(v, "value") else v

    if not ticket.assigned_to_user_id:
        return
    try:
        existing = (
            db.query(RoutingFeedback)
            .filter(RoutingFeedback.ticket_id == ticket.id)
            .first()
        )
        if existing:
            # Update agent in case of re-assignment
            existing.assigned_agent_id = ticket.assigned_to_user_id
            existing.ticket_type = str(_enum_val(ticket.ticket_type)) if ticket.ticket_type else None
            db.flush()
            return

        category_id = None
        try:
            if ticket.service_item_id:
                from app.models.service_desk import ServiceItem  # noqa: PLC0415
                si = db.query(ServiceItem).filter(ServiceItem.id == ticket.service_item_id).first()
                if si:
                    category_id = si.category_id
        # intentional: best-effort fallback, log noise outweighs diagnostic value
        except Exception:
            pass

        row = RoutingFeedback(
            id=str(uuid.uuid4()),
            ticket_id=ticket.id,
            assigned_agent_id=ticket.assigned_to_user_id,
            ticket_type=str(_enum_val(ticket.ticket_type)) if ticket.ticket_type else None,
            category_id=category_id,
            priority=str(_enum_val(ticket.priority)) if ticket.priority else None,
            support_level=str(_enum_val(ticket.support_level)) if ticket.support_level else None,
        )
        db.add(row)
        db.flush()
    except Exception as exc:
        _logger.warning("record_routing_event failed for ticket %s: %s", ticket.id, exc)


def record_routing_outcome(db: Session, ticket: Ticket) -> None:
    """Fill in resolution outcome on the RoutingFeedback row when ticket closes.

    Call this when ticket status transitions to resolved/closed.
    """
    if not ticket.assigned_to_user_id:
        return
    try:
        row = (
            db.query(RoutingFeedback)
            .filter(RoutingFeedback.ticket_id == ticket.id)
            .first()
        )
        if not row:
            # Create retroactively
            record_routing_event(db, ticket)
            row = (
                db.query(RoutingFeedback)
                .filter(RoutingFeedback.ticket_id == ticket.id)
                .first()
            )
            if not row:
                return

        row.resolution_minutes = ticket.resolution_minutes
        row.csat_score = ticket.csat_score
        row.outcome_recorded_at = datetime.now(timezone.utc)
        db.flush()
    except Exception as exc:
        _logger.warning("record_routing_outcome failed for ticket %s: %s", ticket.id, exc)


def run_outcome_scan(db: Session, batch: int = 200) -> dict:
    """Batch job: fill in outcome data for recently closed tickets missing it.

    Processes up to *batch* tickets where outcome_recorded_at IS NULL.
    Returns {processed, updated, errors}.
    """
    stats = {"processed": 0, "updated": 0, "errors": 0}
    try:
        rows = (
            db.query(RoutingFeedback)
            .filter(RoutingFeedback.outcome_recorded_at.is_(None))
            .limit(batch)
            .all()
        )
        for row in rows:
            try:
                stats["processed"] += 1
                ticket = db.query(Ticket).filter(Ticket.id == row.ticket_id).first()
                if not ticket:
                    continue
                if ticket.status not in (TicketStatus.resolved, TicketStatus.closed):
                    continue
                row.resolution_minutes = ticket.resolution_minutes
                row.csat_score = ticket.csat_score
                row.outcome_recorded_at = datetime.now(timezone.utc)
                db.commit()
                stats["updated"] += 1
            except Exception as exc:
                _logger.error("outcome_scan error on row %s: %s", row.id, exc)
                db.rollback()
                stats["errors"] += 1
    except Exception as exc:
        _logger.error("run_outcome_scan failed: %s", exc)
    return stats


def get_routing_stats(db: Session) -> dict:
    """Return aggregate ML routing statistics for the dashboard."""
    try:
        total_routed = db.query(sqlfunc.count(RoutingFeedback.id)).scalar() or 0
        total_with_outcome = (
            db.query(sqlfunc.count(RoutingFeedback.id))
            .filter(RoutingFeedback.outcome_recorded_at.isnot(None))
            .scalar()
        ) or 0
        avg_resolution = (
            db.query(sqlfunc.avg(RoutingFeedback.resolution_minutes))
            .filter(RoutingFeedback.resolution_minutes.isnot(None))
            .scalar()
        )
        avg_csat = (
            db.query(sqlfunc.avg(RoutingFeedback.csat_score))
            .filter(RoutingFeedback.csat_score.isnot(None))
            .scalar()
        )

        # Top 5 agents by avg resolution speed (min samples)
        top_agents = (
            db.query(
                RoutingFeedback.assigned_agent_id,
                sqlfunc.avg(RoutingFeedback.resolution_minutes).label("avg_minutes"),
                sqlfunc.count(RoutingFeedback.id).label("total"),
            )
            .filter(RoutingFeedback.resolution_minutes.isnot(None))
            .group_by(RoutingFeedback.assigned_agent_id)
            .having(sqlfunc.count(RoutingFeedback.id) >= _MIN_SAMPLES)
            .order_by(sqlfunc.avg(RoutingFeedback.resolution_minutes))
            .limit(5)
            .all()
        )

        return {
            "total_routing_events": total_routed,
            "total_with_outcome": total_with_outcome,
            "coverage_pct": round((total_with_outcome / total_routed) * 100, 1) if total_routed else 0,
            "global_avg_resolution_minutes": round(float(avg_resolution), 1) if avg_resolution else None,
            "global_avg_csat": round(float(avg_csat), 2) if avg_csat else None,
            "top_agents_by_speed": [
                {
                    "agent_id": row.assigned_agent_id,
                    "avg_resolution_minutes": round(float(row.avg_minutes), 1),
                    "total_tickets": row.total,
                }
                for row in top_agents
            ],
        }
    except Exception as exc:
        _logger.error("get_routing_stats failed: %s", exc)
        return {"error": str(exc)}
