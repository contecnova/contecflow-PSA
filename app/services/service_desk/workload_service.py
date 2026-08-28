from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models.service_desk import AgentGroup, AgentGroupMember, Ticket, TicketPriority, TicketStatus
from app.models.user import User
from app.services.sla_service import log_history
import logging

logger = logging.getLogger(__name__)


def get_group_with_members_or_404(db: Session, group_id: str) -> AgentGroup:
    group = db.query(AgentGroup).options(
        joinedload(AgentGroup.members).joinedload(AgentGroupMember.user)
    ).filter(AgentGroup.id == group_id).first()
    if not group:
        raise HTTPException(404)
    return group


def _count_open_tickets_for_user(db: Session, user_id: str) -> int:
    return db.query(func.count(Ticket.id)).filter(
        Ticket.assigned_to_user_id == user_id,
        Ticket.status.not_in([TicketStatus.resolved, TicketStatus.closed, TicketStatus.cancelled]),
    ).scalar() or 0


def _count_p1_tickets_for_user(db: Session, user_id: str) -> int:
    return db.query(func.count(Ticket.id)).filter(
        Ticket.assigned_to_user_id == user_id,
        Ticket.priority == TicketPriority.p1_critical,
        Ticket.status.not_in([TicketStatus.resolved, TicketStatus.closed, TicketStatus.cancelled]),
    ).scalar() or 0


def build_group_workload_response(db: Session, group: AgentGroup, group_id: str) -> dict:
    result = []
    for member in group.members:
        open_count = _count_open_tickets_for_user(db, member.user_id)
        p1_count = _count_p1_tickets_for_user(db, member.user_id)
        result.append(
            {
                "user_id": member.user_id,
                "user_name": member.user.full_name if member.user else None,
                "is_lead": member.is_lead,
                "open_tickets": open_count,
                "p1_tickets": p1_count,
            }
        )

    result.sort(key=lambda x: x["open_tickets"])
    return {
        "group_id": group_id,
        "group_name": group.name,
        "agents": result,
        "recommended_assignee": result[0] if result else None,
    }


def get_group_workload_payload(db: Session, group_id: str) -> dict:
    group = get_group_with_members_or_404(db, group_id)
    return build_group_workload_response(db, group, group_id)


def get_ticket_for_auto_assign_or_404(db: Session, ticket_id: str) -> Ticket:
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(404)
    if not ticket.assigned_group_id:
        raise HTTPException(400, "El ticket no tiene grupo asignado. Asigna un grupo primero.")
    return ticket


def get_group_members_or_400(db: Session, group_id: str):
    members = db.query(AgentGroupMember).filter(AgentGroupMember.group_id == group_id).all()
    if not members:
        raise HTTPException(400, "El grupo no tiene agentes")
    return members


def select_best_agent_id_by_open_load(db: Session, members) -> str:
    best_agent_id = None
    best_count = float("inf")
    for member in members:
        count = _count_open_tickets_for_user(db, member.user_id)
        if count < best_count:
            best_count = count
            best_agent_id = member.user_id
    return best_agent_id


def apply_auto_assignment(ticket: Ticket, best_agent_id: str):
    old_assignee = ticket.assigned_to_user_id
    ticket.assigned_to_user_id = best_agent_id
    if ticket.status == TicketStatus.new:
        ticket.status = TicketStatus.assigned
    return old_assignee


def prepare_auto_assignment(db: Session, ticket_id: str):
    ticket = get_ticket_for_auto_assign_or_404(db, ticket_id)
    members = get_group_members_or_400(db, ticket.assigned_group_id)
    best_agent_id = select_best_agent_id_by_open_load(db, members)
    old_assignee = apply_auto_assignment(ticket, best_agent_id)
    return ticket, old_assignee, best_agent_id


def get_user_name_by_id(db: Session, user_id: str):
    user = db.query(User).filter(User.id == user_id).first()
    return user.full_name if user else None


def auto_assign_ticket_command(db: Session, ticket_id: str, current_user_id: str) -> dict:
    ticket, old_assignee, best_agent_id = prepare_auto_assignment(db, ticket_id)
    log_history(db, ticket.id, "assigned_to_user_id", old_assignee, best_agent_id, current_user_id)
    return {"ok": True, "assigned_to": best_agent_id, "agent_name": get_user_name_by_id(db, best_agent_id)}


# ── ML-enhanced routing ───────────────────────────────────────────────────────

def _agent_csat_score(db: Session, user_id: str) -> float:
    """Return the average CSAT score (0-5) for closed tickets assigned to *user_id*.

    Returns 3.0 (neutral) when there is no CSAT history.
    """
    try:
        from sqlalchemy import func as _func
        avg = (
            db.query(_func.avg(Ticket.csat_score))
            .filter(
                Ticket.assigned_to_user_id == user_id,
                Ticket.csat_score.isnot(None),
            )
            .scalar()
        )
        return float(avg) if avg is not None else 3.0
    except Exception:
        return 3.0


def _agent_skills_match(db: Session, user_id: str, ticket_category: str | None) -> float:
    """Return a skill-match fraction (0-1) based on whether the agent has skills
    relevant to the ticket category.

    Uses a simple keyword overlap between skill names and the ticket category.
    Returns 0.5 when category is None or skills cannot be determined.
    """
    if not ticket_category:
        return 0.5
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return 0.5
        skills = getattr(user, "skills", []) or []
        if not skills:
            return 0.5

        cat_words = set(ticket_category.lower().split())
        for skill in skills:
            skill_name = (getattr(skill, "name", "") or "").lower()
            if any(word in skill_name for word in cat_words):
                return 1.0
        # Partial match: any shared word
        for skill in skills:
            skill_name = (getattr(skill, "name", "") or "").lower()
            if any(word in skill_name for word in cat_words if len(word) > 3):
                return 0.7
        return 0.3
    except Exception:
        return 0.5


def score_agent_for_ticket(db: Session, user_id: str, ticket: Ticket) -> float:
    """Compute a composite 0-1 routing score for assigning *ticket* to *user_id*.

    Formula:
      - Skill match (40%): keyword overlap agent_skills ↔ ticket category (derived via service_item.category_id or ticket_type)
      - Availability (30%): 1 - (open_tickets / max_capacity_10)
      - CSAT quality (30%): avg_csat / 5
    """
    open_tickets = _count_open_tickets_for_user(db, user_id)
    max_capacity = 10
    availability = max(0.0, (max_capacity - open_tickets) / max_capacity)

    csat = _agent_csat_score(db, user_id)
    csat_norm = csat / 5.0

    # FIX: Ticket no tiene .category directa — derivamos de service_item o
    # ticket_type. Sin esta corrección saltaba AttributeError al routear.
    _si = getattr(ticket, "service_item", None)
    _cat_id = getattr(_si, "category_id", None) if _si is not None else None
    if _cat_id:
        _cat_name = getattr(_si, "name", None) or str(_cat_id)
    elif getattr(ticket, "ticket_type", None) is not None:
        _tt = ticket.ticket_type
        _cat_name = str(getattr(_tt, "value", _tt))
    else:
        _cat_name = None
    skill_match = _agent_skills_match(db, user_id, _cat_name)

    score = skill_match * 0.40 + availability * 0.30 + csat_norm * 0.30
    return round(score, 4)


def select_best_agent_ml(db: Session, members, ticket: Ticket) -> str:
    """Select the best agent using ML composite score (skills + availability + CSAT).

    Falls back to open-load balancing if scoring fails.
    """
    try:
        best_id = None
        best_score = -1.0
        for member in members:
            s = score_agent_for_ticket(db, member.user_id, ticket)
            if s > best_score:
                best_score = s
                best_id = member.user_id
        if best_id:
            return best_id
    # intentional: best-effort fallback, log noise outweighs diagnostic value
    except Exception:
        logger.debug("select_best_agent_ml: fallo best-effort ignorado", exc_info=True)
    # fallback
    return select_best_agent_id_by_open_load(db, members)


def auto_assign_ticket_ml_command(db: Session, ticket_id: str, current_user_id: str) -> dict:
    """Auto-assign a ticket using ML-enhanced routing (availability + history + CSAT + skills).

    Records a RoutingFeedback event for the chosen assignment.
    """
    from app.services.service_desk.ml_routing_service import (
        predict_best_agent,
        record_routing_event,
        get_routing_candidates,
    )

    ticket = get_ticket_for_auto_assign_or_404(db, ticket_id)
    members = get_group_members_or_400(db, ticket.assigned_group_id)

    candidates = get_routing_candidates(db, ticket, members)
    best_agent_id = predict_best_agent(db, ticket, members)

    if not best_agent_id:
        raise HTTPException(400, "No hay agentes disponibles para este ticket")

    old_assignee = apply_auto_assignment(ticket, best_agent_id)
    log_history(db, ticket.id, "assigned_to_user_id", old_assignee, best_agent_id, current_user_id)
    record_routing_event(db, ticket)

    best_candidate = next((c for c in candidates if c["user_id"] == best_agent_id), {})

    return {
        "ok": True,
        "assigned_to": best_agent_id,
        "agent_name": get_user_name_by_id(db, best_agent_id),
        "method": "ml_score_v2",
        "composite_score": best_candidate.get("composite_score"),
        "components": best_candidate.get("components"),
    }


