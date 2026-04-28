"""
Change Impact Analysis Endpoints
=================================
POST /sd/changes/{change_id}/impact-analysis  — run automated analysis
GET  /sd/changes/{change_id}/impact-analysis  — get cached results
GET  /sd/changes/{change_id}/risk-matrix      — per-CI risk matrix
POST /sd/changes/{change_id}/rollback-plan    — generate rollback procedure
GET  /sd/changes/{change_id}/rollback-plan    — get cached rollback plan
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.services.service_desk.change_impact_service import (
    analyze_change_impact_full,
    get_cached_impact_analysis,
    generate_rollback_plan,
    get_risk_matrix_for_change,
)
from app.services.service_desk.change_impact_service import (
    _get_json_setting,  # noqa: PLC2403
)

router = APIRouter(prefix="/sd/changes", tags=["change-impact"])


@router.post("/{change_id}/impact-analysis", summary="Run automated change impact analysis")
def run_impact_analysis(
    change_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return analyze_change_impact_full(db, change_id, current_user_id=str(current_user.id))


@router.get("/{change_id}/impact-analysis", summary="Get cached change impact analysis")
def get_impact_analysis(
    change_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return get_cached_impact_analysis(db, change_id)


@router.get("/{change_id}/risk-matrix", summary="Per-CI risk matrix for change")
def risk_matrix(
    change_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return {"change_id": change_id, "risk_matrix": get_risk_matrix_for_change(db, change_id)}


@router.post("/{change_id}/rollback-plan", summary="Generate rollback plan")
def generate_rollback(
    change_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return generate_rollback_plan(db, change_id, current_user_id=str(current_user.id))


@router.get("/{change_id}/rollback-plan", summary="Get cached rollback plan")
def get_rollback_plan(
    change_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    from fastapi import HTTPException  # noqa: PLC0415
    plan = _get_json_setting(db, f"sd.change.rollback.{change_id}")
    if not plan:
        raise HTTPException(404, "Rollback plan no encontrado. Ejecuta POST primero.")
    return plan
