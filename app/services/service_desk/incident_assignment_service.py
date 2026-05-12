"""
incident_assignment_service.py — ML-enhanced incident assignment.

Uses a scoring model to recommend the best agent/group for an incoming ticket
based on:
  - Historical assignment patterns by category/keywords
  - Agent current workload and capacity
  - Skill matching (from skills.py)
  - Priority urgency balancing
  - On-call schedule

When LightGBM is available, uses a trained classifier. Otherwise falls back
to rule-based weighted scoring.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.settings import AppSetting

try:
    import lightgbm as lgb  # type: ignore
    _LGBM_AVAILABLE = True
except (ImportError, OSError):
    _LGBM_AVAILABLE = False

_KEY_ASSIGNMENT_STATS = "sd.ml_assignment.stats"
_KEY_ASSIGNMENT_MODEL = "sd.ml_assignment.model_meta"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _keyword_category_score(title: str, description: str, agent_specializations: list[str]) -> float:
    """Keyword overlap score between ticket and agent specializations."""
    text = (title + " " + description).lower()
    if not agent_specializations:
        return 0.5
    matches = sum(1 for s in agent_specializations if s.lower() in text)
    return min(1.0, matches / len(agent_specializations) + 0.1)


def _workload_score(active_tickets: int, capacity: int) -> float:
    """Inverse workload score — lower load = higher score."""
    if capacity <= 0:
        return 0.0
    ratio = active_tickets / capacity
    return max(0.0, 1.0 - ratio)


def recommend_assignment(
    db: Session,
    *,
    ticket_id: str,
    title: str,
    description: str,
    priority: str,
    ticket_type: str,
    org_id: Optional[str],
    candidate_agents: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Recommend assignment for a ticket.

    candidate_agents format:
      [{
        "user_id": str,
        "name": str,
        "active_tickets": int,
        "capacity": int,
        "specializations": [str],
        "is_on_call": bool,
        "group_id": Optional[str],
      }]

    Returns:
      {
        recommended_user_id, recommended_name, confidence, all_scores,
        method_used, reasoning
      }
    """
    from app.models.service_desk import AgentGroupMember, Ticket  # noqa: PLC0415
    from app.services.service_desk.ml_routing_service import (  # noqa: PLC0415
        get_routing_candidates,
        predict_best_agent,
    )

    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")

    members: list[Any] = []
    if ticket.assigned_group_id:
        members = (
            db.query(AgentGroupMember)
            .filter(AgentGroupMember.group_id == ticket.assigned_group_id)
            .all()
        )
    elif candidate_agents:
        class _MemberProxy:
            def __init__(self, user_id: str):
                self.user_id = user_id

        members = [_MemberProxy(str(a.get("user_id"))) for a in candidate_agents if a.get("user_id")]
    else:
        all_members = db.query(AgentGroupMember).all()
        seen: set[str] = set()
        for m in all_members:
            if m.user_id in seen:
                continue
            seen.add(m.user_id)
            members.append(m)

    if not members:
        return {
            "recommended_user_id": None,
            "recommended_name": None,
            "confidence": 0.0,
            "all_scores": [],
            "recommendations": [],
            "method_used": "no_candidates",
            "reasoning": "No candidate agents available",
            "lgbm_available": _LGBM_AVAILABLE,
        }

    ranked = get_routing_candidates(db, ticket, members)
    best_user_id = predict_best_agent(db, ticket, members)
    best = next((c for c in ranked if c.get("user_id") == best_user_id), ranked[0] if ranked else None)

    if not best:
        return {
            "recommended_user_id": None,
            "recommended_name": None,
            "confidence": 0.0,
            "all_scores": [],
            "recommendations": [],
            "method_used": "no_candidates",
            "reasoning": "No eligible candidates",
            "lgbm_available": _LGBM_AVAILABLE,
        }

    scores = [
        {
            "user_id": c.get("user_id"),
            "name": c.get("user_name"),
            "score": c.get("composite_score", 0.0),
            "available": c.get("available", False),
            "components": c.get("components", {}),
        }
        for c in ranked
    ]

    # Record stat
    stats: dict = _get_setting(db, _KEY_ASSIGNMENT_STATS, org_id)
    stats["total_recommendations"] = stats.get("total_recommendations", 0) + 1
    stats["last_recommendation_at"] = _iso_now()
    _set_setting(db, _KEY_ASSIGNMENT_STATS, org_id, stats)

    return {
        "recommended_user_id": best.get("user_id"),
        "recommended_name": best.get("user_name"),
        "confidence": best.get("composite_score", 0.0),
        "all_scores": scores,
        "recommendations": scores,
        "method_used": "ml_score_v2",
        "reasoning": (
            "Top score ML: "
            f"availability={best.get('components', {}).get('availability')}, "
            f"historical_speed={best.get('components', {}).get('historical_speed')}, "
            f"historical_csat={best.get('components', {}).get('historical_csat')}, "
            f"skill_match={best.get('components', {}).get('skill_match')}"
        ),
        "lgbm_available": _LGBM_AVAILABLE,
    }


def get_assignment_stats(db: Session, *, org_id: Optional[str]) -> dict:
    """Aggregate stats for the ML assignment dashboard.

    Returns counters of past recommendations PLUS real-time agent_loads for SD
    agents (so the UI can render a workload chart and use them as candidates
    for a new recommendation).
    """
    from sqlalchemy import func as sqlfunc  # noqa: PLC0415

    from app.models.service_desk import (  # noqa: PLC0415
        Ticket, TicketStatus, AgentGroupMember,
    )
    from app.models.user import User  # noqa: PLC0415

    stats = _get_setting(db, _KEY_ASSIGNMENT_STATS, org_id)

    # Build agent_loads: every user who is a member of any SD agent group
    # (i.e. an actual SD agent), with their current open-ticket count and
    # specialisations from the group memberships.
    members_q = db.query(AgentGroupMember).join(User, AgentGroupMember.user_id == User.id)
    if org_id:
        members_q = members_q.filter(User.organization_id == org_id)
    members = members_q.all()

    if members:
        # Open ticket counts per assignee in a single query
        active_states = [TicketStatus.resolved, TicketStatus.closed, TicketStatus.cancelled]
        load_q = (
            db.query(Ticket.assigned_to_user_id, sqlfunc.count(Ticket.id).label("cnt"))
            .filter(Ticket.assigned_to_user_id.isnot(None))
            .filter(Ticket.status.notin_(active_states))
        )
        # FIX: Ticket no tiene columna organization_id propia (la org se deriva
        # vía Project.organization_id o Client.organization_id). Hacemos JOIN
        # opcional con Project; los tickets sin project son del propio user
        # asignado, ya filtrado upstream por agent groups de la org.
        if org_id:
            from app.models.project import Project as _Project  # noqa: PLC0415
            from sqlalchemy import or_ as _or  # noqa: PLC0415
            load_q = load_q.outerjoin(_Project, Ticket.project_id == _Project.id).filter(
                _or(Ticket.project_id.is_(None), _Project.organization_id == org_id)
            )
        load_q = load_q.group_by(Ticket.assigned_to_user_id)
        load_by_user: dict[str, int] = {row.assigned_to_user_id: int(row.cnt or 0) for row in load_q.all()}

        # Aggregate by user (a user may appear in several groups)
        agg: dict[str, dict[str, Any]] = {}
        for m in members:
            uid = m.user_id
            if not m.user:
                continue
            if uid not in agg:
                agg[uid] = {
                    "user_id": uid,
                    "agent_id": uid,
                    "agent_name": m.user.full_name or m.user.email or uid,
                    "name": m.user.full_name or m.user.email or uid,
                    "open_tickets": load_by_user.get(uid, 0),
                    "active_tickets": load_by_user.get(uid, 0),
                    "capacity": int(getattr(m.user, "weekly_capacity_hours", 40) or 40) // 4 or 10,
                    "specializations": [],
                    "is_on_call": False,
                    "groups": [],
                }
            if m.group and m.group.name and m.group.name not in agg[uid]["groups"]:
                agg[uid]["groups"].append(m.group.name)
                # Treat group name as a soft specialisation tag
                agg[uid]["specializations"].append(m.group.name.lower())

        # Open tickets unassigned (any SD ticket without assignee, in open state)
        unassigned_q = db.query(sqlfunc.count(Ticket.id)).filter(
            Ticket.assigned_to_user_id.is_(None),
            Ticket.status.notin_(active_states),
        )
        if org_id:
            # FIX: Ticket no tiene organization_id propia; scope vía Project.
            from app.models.project import Project as _Project  # noqa: PLC0415
            from sqlalchemy import or_ as _or  # noqa: PLC0415
            unassigned_q = unassigned_q.outerjoin(
                _Project, Ticket.project_id == _Project.id
            ).filter(
                _or(Ticket.project_id.is_(None), _Project.organization_id == org_id)
            )
        total_unassigned = int(unassigned_q.scalar() or 0)

        agent_loads = sorted(agg.values(), key=lambda a: a["open_tickets"], reverse=True)
    else:
        agent_loads = []
        total_unassigned = 0

    return {
        **stats,
        "agent_loads": agent_loads,
        "total_unassigned": total_unassigned,
        "lgbm_available": _LGBM_AVAILABLE,
    }


def _get_setting(db: Session, key: str, org_id: Optional[str]) -> dict:
    q = db.query(AppSetting).filter(AppSetting.key == key)
    q = q.filter(AppSetting.organization_id == org_id) if org_id else q.filter(AppSetting.organization_id.is_(None))
    row = q.first()
    if not row or not row.value:
        return {}
    try:
        return json.loads(row.value)
    except Exception:
        return {}


def _set_setting(db: Session, key: str, org_id: Optional[str], value: dict) -> None:
    payload = json.dumps(value, ensure_ascii=False)
    q = db.query(AppSetting).filter(AppSetting.key == key)
    q = q.filter(AppSetting.organization_id == org_id) if org_id else q.filter(AppSetting.organization_id.is_(None))
    row = q.first()
    if not row:
        row = AppSetting(key=key, organization_id=org_id, value=payload, description=f"SD ML Assignment: {key}")
        db.add(row)
    else:
        row.value = payload
    db.commit()
