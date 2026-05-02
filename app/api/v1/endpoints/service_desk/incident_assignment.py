"""
incident_assignment.py — ML-enhanced incident assignment REST endpoints.

Routes:
  POST /sd/tickets/{ticket_id}/recommend-assignment — get ML recommendation
  GET  /sd/assignment/stats                         — assignment model stats
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.ratelimit import limiter
from app.db.session import get_db
from app.models.user import User
from app.services.service_desk.incident_assignment_service import (
    recommend_assignment,
    get_assignment_stats,
)

router = APIRouter(tags=["Service Desk - ML Assignment"])


class CandidateAgentIn(BaseModel):
    user_id: str
    name: str = ""
    active_tickets: int = 0
    capacity: int = 10
    specializations: list[str] = Field(default_factory=list)
    is_on_call: bool = False
    group_id: Optional[str] = None


class AssignmentRequestIn(BaseModel):
    title: str = Field(default="", max_length=500)
    description: str = ""
    priority: str = "p3_medium"
    ticket_type: str = "incident"
    candidate_agents: list[CandidateAgentIn] = Field(default_factory=list, max_length=50)


@router.post(
    "/tickets/{ticket_id}/recommend-assignment",
    summary="Recomendación ML de asignación de ticket",
)
@router.post(
    "/incidents/{ticket_id}/assign/recommend",
    summary="Recomendación ML de asignación de ticket (compat)",
)
@limiter.limit("30/minute")
def recommend_ticket_assignment(
    request: Request,
    ticket_id: str,
    body: AssignmentRequestIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return recommend_assignment(
        db,
        ticket_id=ticket_id,
        title=body.title,
        description=body.description,
        priority=body.priority,
        ticket_type=body.ticket_type,
        org_id=org_id,
        candidate_agents=[a.model_dump() for a in body.candidate_agents],
    )


@router.get("/assignment/stats", summary="Estadísticas del motor de asignación ML")
@router.get("/incidents/assign/stats", summary="Estadísticas del motor de asignación ML (compat)")
@limiter.limit("60/minute")
def assignment_stats(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return get_assignment_stats(db, org_id=org_id)
