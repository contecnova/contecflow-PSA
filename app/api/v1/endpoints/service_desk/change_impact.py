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

from fastapi import APIRouter, Depends, Query
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


# ── ITSM-P05: CAB dashboard + batch score ─────────────────────────────────────

@router.get("/cab-dashboard", summary="CAB dashboard — cambios pendientes con risk score (ITSM-P05)")
def cab_dashboard(
    status: str = Query("submitted,in_approval", description="Comma-separated statuses"),
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
    from app.models.service_desk import ITSMChangeRequest, ChangeStatus  # noqa: PLC0415
    from app.services.service_desk.change_service import serialize_change  # noqa: PLC0415

    requested_statuses = [s.strip() for s in status.split(",") if s.strip()]
    valid_statuses = [
        s for s in requested_statuses
        if s in (st.value for st in ChangeStatus)
    ]
    if not valid_statuses:
        valid_statuses = [ChangeStatus.submitted.value, ChangeStatus.in_approval.value]

    q = (
        db.query(ITSMChangeRequest)
        .filter(ITSMChangeRequest.status.in_(valid_statuses))
    )
    if min_risk_score > 0:
        q = q.filter(
            (ITSMChangeRequest.auto_risk_score >= min_risk_score)
            | ITSMChangeRequest.auto_risk_score.is_(None)
        )

    total = q.count()
    changes = (
        q.order_by(ITSMChangeRequest.auto_risk_score.desc().nullslast())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "unscored": sum(1 for c in changes if c.auto_risk_score is None),
        "items": [serialize_change(c) for c in changes],
    }


@router.post(
    "/batch-score",
    summary="Forzar scoring de todos los cambios pendientes sin score (ITSM-P05)",
)
def batch_score_changes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Scores all submitted/in_approval changes that have no auto_risk_score yet.

    Also auto-approves standard changes with risk score ≤ 30.
    Returns counts of scored and auto-approved changes.
    """
    from app.models.service_desk import ITSMChangeRequest, ChangeStatus  # noqa: PLC0415
    from app.services.service_desk.change_impact_service import score_and_persist  # noqa: PLC0415
    from app.services.service_desk.change_service import _maybe_auto_approve  # noqa: PLC0415

    pending = (
        db.query(ITSMChangeRequest)
        .filter(
            ITSMChangeRequest.status.in_(
                [ChangeStatus.submitted, ChangeStatus.in_approval]
            ),
            ITSMChangeRequest.auto_risk_score.is_(None),
        )
        .all()
    )

    scored = auto_approved = errors = 0
    for change in pending:
        try:
            score_and_persist(db, change.id)
            if _maybe_auto_approve(db, change, system_user_id=str(current_user.id)):
                auto_approved += 1
            db.commit()
            scored += 1
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            errors += 1

    return {
        "ok": True,
        "total_pending": len(pending),
        "scored": scored,
        "auto_approved": auto_approved,
        "errors": errors,
    }
