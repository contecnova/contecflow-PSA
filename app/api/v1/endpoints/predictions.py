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
from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any
import json

from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager
from app.models.user import User
from app.services import ml_trainer

router = APIRouter(tags=["AI Predictions"])


@router.post("/overrun-risk", summary="Predicción ML de sobrecosto/retraso por proyecto")
async def overrun_risk(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        body = await request.json()
    except Exception:
        return {
            "error": "Invalid JSON body",
            "risk_level": "unknown",
            "can_predict": False,
        }
    
    project_id = body.get("project_id") if isinstance(body, dict) else None
    
    if not project_id:
        return {
            "error": "Missing project_id in request body",
            "risk_level": "unknown",
            "can_predict": False,
        }
    
    result = ml_trainer.predict_project(db, project_id, current_user.organization_id)
    if "error" in result:
        # Return 200 with error flag instead of 422 to avoid spam warnings
        return {
            "project_id": project_id,
            "error": result["error"],
            "risk_level": "unknown",
            "can_predict": False,
        }
    return result


@router.get("/portfolio-risk", summary="Resumen de riesgo de toda la cartera de proyectos")
def portfolio_risk(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return ml_trainer.portfolio_risk_summary(db, current_user.organization_id)


@router.post("/train", summary="Reentrenar modelo ML de predicción")
def train_model(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    result = ml_trainer.train_model(db, current_user.organization_id)
    return result


@router.get("/models", summary="Listar versiones del modelo ML")
def list_models(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return ml_trainer.list_models(db, current_user.organization_id)


@router.get("/logs", summary="Historial de predicciones ML")
def prediction_logs(
    project_id: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return ml_trainer.get_prediction_logs(db, current_user.organization_id, project_id=project_id, limit=limit)
