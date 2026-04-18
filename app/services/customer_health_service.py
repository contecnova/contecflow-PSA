"""Customer Health Score service.

Computes a composite health score for a client based on NPS, delivery
performance, budget adherence, ticket resolution and portal activity.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict

from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.models.clients import Client
from app.models.nps import ClientNPS
from app.core.config import settings

logger = logging.getLogger(__name__)


def compute_composite_health(client_id: str, db: Session) -> dict:

    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(404, "Client not found")

    s = settings
    components: Dict[str, Any] = {}

    # NPS
    cutoff_nps = datetime.utcnow() - timedelta(days=s.HEALTH_NPS_LOOKBACK_DAYS)
    nps_responses = db.query(ClientNPS).filter(
        ClientNPS.client_id == client_id,
        ClientNPS.created_at >= cutoff_nps,
    ).all()
    if nps_responses:
        promoters  = sum(1 for r in nps_responses if r.score >= 9)
        detractors = sum(1 for r in nps_responses if r.score <= 6)
        n = len(nps_responses)
        raw_nps = ((promoters - detractors) / n) * 100
        nps_component = round(((raw_nps + 100) / 2), 1)
        components["nps"] = {"value": nps_component, "weight": s.HEALTH_WEIGHT_NPS,
                              "responses": n, "raw_nps": round(raw_nps, 1)}
    else:
        nps_component = 50.0
        components["nps"] = {"value": 50.0, "weight": s.HEALTH_WEIGHT_NPS, "responses": 0, "note": "no_data"}

    # Delivery
    try:
        from app.models.project import Project
        from app.models.financial import ProjectMilestone
        projects = db.query(Project).filter(Project.client_id == client_id).all()
        proj_ids = [p.id for p in projects]
        if proj_ids:
            all_milestones = db.query(ProjectMilestone).filter(
                ProjectMilestone.project_id.in_(proj_ids)
            ).all() if hasattr(ProjectMilestone, "project_id") else []
            done = [m for m in all_milestones
                    if str(getattr(m, "status", "")).lower() in ("completed", "done", "approved")]
            on_time = [m for m in done
                       if hasattr(m, "due_date") and hasattr(m, "completed_at")
                       and m.completed_at and m.due_date
                       and m.completed_at.date() <= m.due_date]
            delivery = round((len(on_time) / max(len(done), 1)) * 100, 1) if done else s.HEALTH_DEFAULT_NO_DATA
        else:
            delivery = s.HEALTH_DEFAULT_NO_DATA
            projects = []
    except Exception:
        delivery = s.HEALTH_DEFAULT_NO_DATA
        projects = []
    components["delivery"] = {"value": delivery, "weight": s.HEALTH_WEIGHT_DELIVERY}

    # Budget
    try:
        in_budget = sum(1 for p in projects
                        if hasattr(p, "budget") and hasattr(p, "actual_cost")
                        and p.budget and p.actual_cost is not None
                        and p.actual_cost <= p.budget)
        budget_score = round((in_budget / max(len(projects), 1)) * 100, 1) if projects else s.HEALTH_DEFAULT_NO_DATA
    except Exception:
        budget_score = s.HEALTH_DEFAULT_NO_DATA
    components["budget"] = {"value": budget_score, "weight": s.HEALTH_WEIGHT_BUDGET}

    # Ticket resolution
    cutoff_tickets = datetime.utcnow() - timedelta(days=s.HEALTH_TICKET_LOOKBACK_DAYS)
    try:
        from app.models.service_desk import Ticket
        recent_tickets = db.query(Ticket).filter(Ticket.created_at >= cutoff_tickets).all()
        client_tickets = [t for t in recent_tickets
                          if hasattr(t, "client_id") and t.client_id == client_id]
        if not client_tickets:
            client_tickets = recent_tickets[:50]
        resolved = [t for t in client_tickets
                    if str(getattr(t.status, "value", t.status)) in ("resolved", "closed")]
        sla_ok = [t for t in resolved
                  if hasattr(t, "sla_breached") and not t.sla_breached]
        ticket_score = round((len(sla_ok) / max(len(resolved), 1)) * 100, 1) if resolved else s.HEALTH_DEFAULT_NO_DATA
    except Exception:
        ticket_score = s.HEALTH_DEFAULT_NO_DATA
    components["ticket_resolution"] = {"value": ticket_score, "weight": s.HEALTH_WEIGHT_TICKETS}

    # Portal activity
    try:
        from app.models.client_portal import PortalSession
        portal_sessions = db.query(PortalSession).filter(
            PortalSession.client_id == client_id,
            PortalSession.created_at >= cutoff_tickets,
        ).count() if hasattr(PortalSession, "client_id") else 0
        portal_score = min(100.0, s.HEALTH_PORTAL_BASE_SCORE + (portal_sessions * s.HEALTH_PORTAL_SCORE_PER_SESSION))
    except Exception:
        portal_score = 50.0
    components["portal_activity"] = {"value": portal_score, "weight": s.HEALTH_WEIGHT_PORTAL}

    composite = round(
        nps_component * s.HEALTH_WEIGHT_NPS +
        delivery      * s.HEALTH_WEIGHT_DELIVERY +
        budget_score  * s.HEALTH_WEIGHT_BUDGET +
        ticket_score  * s.HEALTH_WEIGHT_TICKETS +
        portal_score  * s.HEALTH_WEIGHT_PORTAL,
        1,
    )
    composite = max(0.0, min(100.0, composite))
    category = ("excellent" if composite >= s.HEALTH_THRESHOLD_EXCELLENT else
                 "good"      if composite >= s.HEALTH_THRESHOLD_GOOD else
                 "at_risk"   if composite >= s.HEALTH_THRESHOLD_AT_RISK else
                 "critical")

    return {
        "client_id": client_id,
        "composite_score": composite,
        "category": category,
        "components": components,
        "computed_at": str(datetime.utcnow()),
    }
