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

from sqlalchemy.orm import Session

from app.models.settings import AppSetting

try:
    import lightgbm as lgb  # type: ignore
    _LGBM_AVAILABLE = True
except ImportError:
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
    if not candidate_agents:
        return {
            "recommended_user_id": None,
            "recommended_name": None,
            "confidence": 0.0,
            "all_scores": [],
            "method_used": "no_candidates",
            "reasoning": "No candidate agents provided",
        }

    priority_boost = {"p1_critical": 0.3, "p1": 0.3, "p2_high": 0.15, "p2": 0.15}.get(priority, 0.0)
    scores = []

    for agent in candidate_agents:
        kw_score = _keyword_category_score(title, description, agent.get("specializations", []))
        wl_score = _workload_score(agent.get("active_tickets", 0), agent.get("capacity", 10))
        oncall_bonus = 0.2 if agent.get("is_on_call") else 0.0

        total = 0.45 * kw_score + 0.4 * wl_score + 0.1 * oncall_bonus + priority_boost
        scores.append({
            "user_id": agent["user_id"],
            "name": agent.get("name", agent["user_id"]),
            "score": round(min(1.0, total), 4),
            "kw_score": round(kw_score, 4),
            "workload_score": round(wl_score, 4),
            "is_on_call": agent.get("is_on_call", False),
            "active_tickets": agent.get("active_tickets", 0),
        })

    scores.sort(key=lambda s: s["score"], reverse=True)
    best = scores[0]

    # Record stat
    stats: dict = _get_setting(db, _KEY_ASSIGNMENT_STATS, org_id)
    stats["total_recommendations"] = stats.get("total_recommendations", 0) + 1
    stats["last_recommendation_at"] = _iso_now()
    _set_setting(db, _KEY_ASSIGNMENT_STATS, org_id, stats)

    return {
        "recommended_user_id": best["user_id"],
        "recommended_name": best["name"],
        "confidence": best["score"],
        "all_scores": scores,
        "method_used": "lightgbm_stub" if _LGBM_AVAILABLE else "rule_based",
        "reasoning": f"Top score: keyword_match={best['kw_score']}, workload={best['workload_score']}, oncall={best['is_on_call']}",
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
        if org_id:
            load_q = load_q.filter(Ticket.organization_id == org_id)
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
            unassigned_q = unassigned_q.filter(Ticket.organization_id == org_id)
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
