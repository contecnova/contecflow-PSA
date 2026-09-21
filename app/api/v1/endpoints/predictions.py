"""
predictions.py — ML-powered project overrun predictions.

Prefix: /predictions  (set in delivery.py)

Routes:
  POST /overrun-risk           — predict single project
  GET  /portfolio-risk         — risk summary across all active projects
  POST /train                  — manually trigger model retraining
  GET  /models                 — list trained models for current org
  GET  /logs                   — recent prediction logs
"""
import logging

from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any

from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager, require_internal_user
from app.core.responses import APIListResponse, APIResponse
from app.models.user import User
from app.services import ml_trainer

logger = logging.getLogger(__name__)

router = APIRouter(tags=["AI Predictions"])


@router.post("/overrun-risk", summary="Predicción ML de sobrecosto/retraso por proyecto")
def overrun_risk(
    body: Dict[str, Any] = Body(default_factory=dict),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: excepcion revisada: calcula una prediccion
):
    # Audit #C7: endpoint converted from async→def. It only does DB work; the
    # previous async wrapper forced sync ORM calls onto the event loop. FastAPI
    # now runs this in the threadpool. Body is parsed by FastAPI/Pydantic.
    project_id = body.get("project_id") if isinstance(body, dict) else None

    if not project_id:
        return APIResponse.ok(data={
            "error": "Missing project_id in request body",
            "risk_level": "unknown",
            "can_predict": False,
        })

    result = ml_trainer.predict_project(
        db, project_id, current_user.organization_id,
        is_superadmin=bool(getattr(current_user, "is_superadmin", False)),
    )
    if "error" in result:
        # Return 200 with error flag instead of 422 to avoid spam warnings
        return APIResponse.ok(data={
            "project_id": project_id,
            "error": result["error"],
            "risk_level": "unknown",
            "can_predict": False,
        })
    return APIResponse.ok(data=result)


@router.get("/portfolio-risk", summary="Resumen de riesgo de toda la cartera de proyectos")
def portfolio_risk(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return APIResponse.ok(data=ml_trainer.portfolio_risk_summary(
        db,
        current_user.organization_id,
        is_superadmin=bool(getattr(current_user, "is_superadmin", False)),
    ))


@router.post("/train", summary="Reentrenar modelo ML de predicción")
def train_model(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    result = ml_trainer.train_model(db, current_user.organization_id)
    return APIResponse.ok(data=result)


@router.get("/models", summary="Listar versiones del modelo ML")
def list_models(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return APIListResponse.ok(items=ml_trainer.list_models(db, current_user.organization_id))


@router.get("/logs", summary="Historial de predicciones ML")
def prediction_logs(
    project_id: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return APIListResponse.ok(items=ml_trainer.get_prediction_logs(db, current_user.organization_id, project_id=project_id, limit=limit))
