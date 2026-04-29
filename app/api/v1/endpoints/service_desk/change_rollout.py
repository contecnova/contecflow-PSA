"""
change_rollout.py — Advanced change rollout planning endpoints.

Routes:
  GET  /sd/changes/{cr_id}/rollout-plans            — list plans for a CR
  POST /sd/changes/{cr_id}/rollout-plans            — create rollout plan
  GET  /sd/changes/rollout-plans/{plan_id}          — get plan detail
  POST /sd/changes/rollout-plans/{plan_id}/approve  — approve plan
  POST /sd/changes/rollout-plans/{plan_id}/advance-phase — advance to next phase
  POST /sd/changes/rollout-plans/simulate           — what-if impact simulation
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.ratelimit import limiter
from app.db.session import get_db
from app.models.user import User
from app.services.service_desk.change_rollout_service import (
    create_rollout_plan,
    get_plan,
    list_plans,
    approve_plan,
    advance_phase,
    simulate_impact,
)

router = APIRouter(prefix="/sd", tags=["Service Desk - Change Rollout"])


class RolloutPhaseIn(BaseModel):
    name: str
    description: str = ""
    target_pct: int = Field(100, ge=1, le=100, description="% of users/services in this phase")
    gate_criteria: list[str] = Field(default_factory=list)
    duration_minutes: int = Field(30, ge=5)


class CommunicationItemIn(BaseModel):
    stakeholder_group: str
    channel: str = Field("email", description="email | slack | teams | sms | jira")
    message_template: str = ""
    send_at: Optional[str] = None


class TestChecklistItemIn(BaseModel):
    test_name: str
    required: bool = True
    automated: bool = False


class CreateRolloutPlanIn(BaseModel):
    title: str = Field(..., min_length=3, max_length=300)
    rollout_phases: list[RolloutPhaseIn] = Field(..., min_length=1, max_length=20)
    rollback_steps: list[str] = Field(default_factory=list)
    testing_checklist: list[TestChecklistItemIn] = Field(default_factory=list)
    communication_plan: list[CommunicationItemIn] = Field(default_factory=list)
    maintenance_window_start: Optional[str] = None
    maintenance_window_end: Optional[str] = None


class AdvancePhaseIn(BaseModel):
    phase_notes: Optional[str] = None


class SimulateImpactIn(BaseModel):
    affected_services: list[str] = Field(default_factory=list)
    affected_users_count: int = Field(0, ge=0)
    change_type: str = Field("normal", pattern="^(standard|normal|emergency)$")
    rollout_phases: list[dict] = Field(default_factory=list)


@router.get("/changes/{cr_id}/rollout-plans", summary="Listar planes de rollout de un CR")
@limiter.limit("60/minute")
def list_rollout_plans(
    request: Request,
    cr_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    items = list_plans(db, org_id=org_id, change_request_id=cr_id)
    return {"items": items, "count": len(items)}


@router.post("/changes/{cr_id}/rollout-plans", summary="Crear plan de rollout para CR", status_code=201)
@limiter.limit("20/minute")
def create_plan(
    request: Request,
    cr_id: str,
    body: CreateRolloutPlanIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return create_rollout_plan(
        db,
        org_id=org_id,
        change_request_id=cr_id,
        title=body.title,
        rollout_phases=[p.model_dump() for p in body.rollout_phases],
        rollback_steps=body.rollback_steps,
        testing_checklist=[t.model_dump() for t in body.testing_checklist],
        communication_plan=[c.model_dump() for c in body.communication_plan],
        maintenance_window_start=body.maintenance_window_start,
        maintenance_window_end=body.maintenance_window_end,
        created_by=current_user.id,
    )


@router.get("/changes/rollout-plans/{plan_id}", summary="Detalle de un plan de rollout")
@limiter.limit("60/minute")
def get_rollout_plan(
    request: Request,
    plan_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        return get_plan(db, org_id=org_id, plan_id=plan_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/changes/rollout-plans/{plan_id}/approve", summary="Aprobar plan de rollout")
@limiter.limit("20/minute")
def approve_rollout_plan(
    request: Request,
    plan_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        return approve_plan(db, org_id=org_id, plan_id=plan_id, approver_user_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/changes/rollout-plans/{plan_id}/advance-phase", summary="Avanzar al siguiente fase de rollout")
@limiter.limit("20/minute")
def advance_rollout_phase(
    request: Request,
    plan_id: str,
    body: AdvancePhaseIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        return advance_phase(db, org_id=org_id, plan_id=plan_id, phase_notes=body.phase_notes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/changes/rollout-plans/simulate", summary="Simulación de impacto de rollout (what-if)")
@limiter.limit("30/minute")
def simulate_rollout_impact(
    request: Request,
    body: SimulateImpactIn,
    current_user: User = Depends(get_current_user),
):
    return simulate_impact(
        affected_services=body.affected_services,
        affected_users_count=body.affected_users_count,
        change_type=body.change_type,
        rollout_phases=body.rollout_phases,
    )
