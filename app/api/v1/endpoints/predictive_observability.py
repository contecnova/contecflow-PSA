"""Predictive Model Observability endpoints.

Expose evaluation health and retraining metadata for ITSM and BI predictive models.
Admin-only — returns per-org state from AppSetting store.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User, UserRole
from app.services.predictive_retraining_service import (
    ITSM_META_KEY,
    BI_META_KEY,
    LAST_EVAL_KEY,
    _get_json,
    evaluate_itsm_model_health,
    evaluate_bi_model_health,
    run_periodic_evaluation_and_retraining,
)

router = APIRouter()

_STATUS_RANK = {
    "healthy": 0,
    "attention": 1,
    "insufficient_data": 2,
}


def _require_admin(current_user: User = Depends(get_current_user)) -> User:
    if getattr(current_user, "role", None) != UserRole.admin:
        raise HTTPException(status_code=403, detail="admin_required")
    return current_user


@router.get(
    "/bi/predictive/observability/status",
    summary="Estado de salud de los modelos predictivos (ITSM + BI)",
    tags=["Predictive Observability"],
)
def predictive_observability_status(
    organization_id: Optional[str] = Query(None, description="Filtrar por organización (admin override)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_admin),
):
    """Return the latest evaluation cycle summary plus per-org retraining metadata.

    - `last_eval`: last `run_periodic_evaluation_and_retraining` execution summary.
    - `itsm_meta`: ITSM model retraining state for the org.
    - `bi_meta`: BI model retraining state for the org.
    """
    org_id: Optional[str] = organization_id or getattr(current_user, "organization_id", None)

    last_eval = _get_json(db, LAST_EVAL_KEY, None, default={})
    itsm_meta = _get_json(db, ITSM_META_KEY, org_id, default={})
    bi_meta = _get_json(db, BI_META_KEY, org_id, default={})

    return {
        "organization_id": org_id,
        "last_eval": last_eval,
        "itsm_meta": itsm_meta,
        "bi_meta": bi_meta,
    }


@router.get(
    "/bi/predictive/observability/health",
    summary="Evaluación de salud en tiempo real de los modelos predictivos",
    tags=["Predictive Observability"],
)
def predictive_observability_health(
    organization_id: Optional[str] = Query(None),
    lookback_days: int = Query(30, ge=1, le=180),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_admin),
):
    """Run and return a fresh health evaluation (read-only, no retraining)."""
    org_id: Optional[str] = organization_id or getattr(current_user, "organization_id", None)

    itsm_eval = evaluate_itsm_model_health(db, organization_id=org_id, lookback_days=lookback_days)
    bi_eval = evaluate_bi_model_health(db, organization_id=org_id)

    overall_score = round((itsm_eval.get("score", 0) + bi_eval.get("score", 0)) / 2, 4)
    statuses = [str(itsm_eval.get("status", "healthy")), str(bi_eval.get("status", "healthy"))]
    overall_status = max(statuses, key=lambda s: _STATUS_RANK.get(s, 0))

    return {
        "organization_id": org_id,
        "overall_score": overall_score,
        "overall_status": overall_status,
        "status_rank": _STATUS_RANK,
        "itsm": itsm_eval,
        "bi": bi_eval,
    }


@router.post(
    "/bi/predictive/observability/trigger-retrain",
    summary="Forzar ciclo de evaluación y retraining (admin)",
    tags=["Predictive Observability"],
)
def predictive_trigger_retrain(
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_admin),
):
    """Manually trigger the full evaluation + conditional retraining cycle.

    Uses the same logic as the Celery beat task but executed synchronously.
    """
    result = run_periodic_evaluation_and_retraining(db)
    return result
