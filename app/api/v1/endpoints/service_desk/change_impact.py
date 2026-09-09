"""
Change Impact Analysis Endpoints
=================================
POST /sd/changes/{change_id}/impact-analysis  — run automated analysis
GET  /sd/changes/{change_id}/impact-analysis  — get cached results
GET  /sd/changes/{change_id}/risk-matrix      — per-CI risk matrix
POST /sd/changes/{change_id}/rollback-plan    — generate rollback procedure
GET  /sd/changes/{change_id}/rollback-plan    — get cached rollback plan

ITSM-P05 additions:
GET  /sd/changes/cab-dashboard                — CAB-ready list with risk scores
POST /sd/changes/batch-score                  — manually trigger batch scoring
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.responses import APIResponse
from app.models.user import User
from app.services.service_desk.change_impact_service import (
    ESTADOS_PENDIENTES_DE_CAB,
    analyze_change_impact_full,
    panel_del_cab,
    puntuar_cambios_pendientes,
    get_cached_impact_analysis,
    generate_rollback_plan,
    get_risk_matrix_for_change,
    generate_testing_plan,
    generate_comms_plan,
    simulate_change_whatif,
)
from app.services.service_desk.change_impact_service import (
    _get_json_setting,
)


class WhatIfIn(BaseModel):
    downtime_minutes: Optional[int] = Field(None, ge=0, le=14400, description="Override downtime in minutes")
    change_type: Optional[str] = Field(None, pattern="^(standard|normal|emergency)$", description="Override change type")
    extra_ci_ids: list[str] = Field(default_factory=list, description="Additional CI IDs to add to affected set")
    remove_ci_ids: list[str] = Field(default_factory=list, description="CI IDs to remove from affected set")
    scheduled_hour_utc: Optional[int] = Field(None, ge=0, le=23, description="Evaluate specific hour for window (0-23)")
    scheduled_dow: Optional[int] = Field(None, ge=0, le=6, description="Evaluate specific day-of-week (0=Monday)")


router = APIRouter(prefix="/sd/changes", tags=["change-impact"])


@router.post("/{change_id}/impact-analysis", summary="Run automated change impact analysis")
def run_impact_analysis(
    change_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return APIResponse.ok(data=analyze_change_impact_full(db, change_id, current_user_id=str(current_user.id)))


@router.get("/{change_id}/impact-analysis", summary="Get cached change impact analysis")
def get_impact_analysis(
    change_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return APIResponse.ok(data=get_cached_impact_analysis(db, change_id))


@router.get("/{change_id}/risk-matrix", summary="Per-CI risk matrix for change")
def risk_matrix(
    change_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return APIResponse.ok(data={"change_id": change_id, "risk_matrix": get_risk_matrix_for_change(db, change_id)})


@router.post("/{change_id}/rollback-plan", summary="Generate rollback plan")
def generate_rollback(
    change_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return APIResponse.ok(data=generate_rollback_plan(db, change_id, current_user_id=str(current_user.id)))


@router.get("/{change_id}/rollback-plan", summary="Get cached rollback plan")
def get_rollback_plan(
    change_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    from fastapi import HTTPException
    plan = _get_json_setting(db, f"sd.change.rollback.{change_id}")
    if not plan:
        raise HTTPException(404, "Rollback plan no encontrado. Ejecuta POST primero.")
    return APIResponse.ok(data=plan)


# ── Testing Plan ──────────────────────────────────────────────────────────────

@router.post("/{change_id}/testing-plan", summary="Generar plan de pruebas estructurado (ITSM-P10)")
def generate_testing_plan_endpoint(
    change_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate a structured testing plan with executable steps for pre/execution/post phases.

    Steps are adapted to the change's risk level and CI count. The plan is cached
    in AppSetting and the change's test_plan text field is also updated if empty.
    """
    return APIResponse.ok(data=generate_testing_plan(db, change_id, current_user_id=str(current_user.id)))


@router.get("/{change_id}/testing-plan", summary="Obtener plan de pruebas en caché (ITSM-P10)")
def get_testing_plan(
    change_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    from fastapi import HTTPException
    plan = _get_json_setting(db, f"sd.change.testing.{change_id}")
    if not plan:
        raise HTTPException(404, "Plan de pruebas no encontrado. Ejecuta POST /testing-plan primero.")
    return APIResponse.ok(data=plan)


# ── Communications Plan ───────────────────────────────────────────────────────

@router.post("/{change_id}/comms-plan", summary="Generar plan de comunicaciones con audiencias y canales (ITSM-P10)")
def generate_comms_plan_endpoint(
    change_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate a structured communications plan adapted to risk level.

    Covers all stakeholder audiences (IT, Service Desk, managers, end users,
    executives for critical changes) with timing (T-7d to T-1h), channel,
    and message templates including rollback notification templates.
    """
    return APIResponse.ok(data=generate_comms_plan(db, change_id, current_user_id=str(current_user.id)))


@router.get("/{change_id}/comms-plan", summary="Obtener plan de comunicaciones en caché (ITSM-P10)")
def get_comms_plan(
    change_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    from fastapi import HTTPException
    plan = _get_json_setting(db, f"sd.change.comms.{change_id}")
    if not plan:
        raise HTTPException(404, "Plan de comunicaciones no encontrado. Ejecuta POST /comms-plan primero.")
    return APIResponse.ok(data=plan)


# ── What-If Simulation ────────────────────────────────────────────────────────

@router.post("/{change_id}/whatif", summary="Simulación what-if de impacto del cambio (ITSM-P10)")
def whatif_simulation(
    change_id: str,
    payload: WhatIfIn,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Simulate hypothetical changes to a Change Request without persisting anything.

    Returns a side-by-side comparison: original vs simulated risk score, label,
    components, CI count, and maintenance window. Optionally evaluates a proposed
    specific time slot (scheduled_hour_utc + scheduled_dow) against the optimal window.

    Useful for answering questions such as:
      - "What if I reduce downtime to 30 min instead of 120 min?"
      - "What if I change the type from 'emergency' to 'normal'?"
      - "What if I schedule on Wednesday at 3 AM — is it better than the suggested window?"
    """
    return APIResponse.ok(data=simulate_change_whatif(db, change_id, overrides=payload.model_dump(exclude_none=True)))


# ── ITSM-P05: CAB dashboard + batch score ─────────────────────────────────────

@router.get("/cab-dashboard", summary="CAB dashboard — cambios pendientes con risk score (ITSM-P05)")
def cab_dashboard(
    # `in_approval` no existe en el enum del modelo: el estado de espera del CAB
    # es `cab_review`. Ver el comentario de `ESTADOS_PENDIENTES_DE_CAB`.
    status: str = Query(
        ",".join(ESTADOS_PENDIENTES_DE_CAB),
        description="Comma-separated statuses"),
    min_risk_score: float = Query(0, ge=0, le=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returns Change Requests pending CAB review, ordered by risk score descending.

    Includes `auto_risk_score`, `auto_risk_label`, `impact_analyzed`, and
    `suggested_window` in every item so the CAB can triage without opening each CR.
    """
    from app.models.service_desk import ChangeStatus

    requested_statuses = [s.strip() for s in status.split(",") if s.strip()]
    valid_statuses = [
        s for s in requested_statuses
        if s in (st.value for st in ChangeStatus)
    ]
    if not valid_statuses:
        # Antes esta rama hacia `ChangeStatus.in_approval.value`, que no existe:
        # un estado inexistente en la peticion devolvia 500 en vez del panel.
        valid_statuses = list(ESTADOS_PENDIENTES_DE_CAB)

    # Objeto (no APIListResponse) para preservar el escalar 'unscored' además de la lista.
    return APIResponse.ok(data=panel_del_cab(
        db, current_user, estados=valid_statuses,
        min_risk_score=min_risk_score, page=page, page_size=page_size))


@router.post(
    "/batch-score",
    summary="Forzar scoring de todos los cambios pendientes sin score (ITSM-P05)",
)
def batch_score_changes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Scores all pending changes that have no auto_risk_score yet.

    Also auto-approves standard changes with risk score ≤ 30.
    Returns counts of scored and auto-approved changes.
    """
    return APIResponse.ok(
        data=puntuar_cambios_pendientes(db, current_user))
