"""
Capacity Planning Endpoints
============================
GET  /sd/capacity/forecast          — ticket volume forecast
GET  /sd/capacity/agents            — per-agent load forecast
GET  /sd/capacity/recommendations   — staffing recommendations
GET  /sd/capacity/burnout-risk      — agent burnout risk score
GET  /sd/capacity/config            — get capacity config
PUT  /sd/capacity/config            — update capacity config
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.responses import APIResponse
from app.models.user import User
from app.services.service_desk.capacity_planning_service import (
    predict_ticket_volume,
    predict_agent_load,
    get_capacity_recommendations,
    calculate_burnout_risk,
    get_capacity_config,
    save_capacity_config,
)
from app.core.deps import require_admin

router = APIRouter(prefix="/capacity", tags=["capacity-planning"])


@router.get("/forecast", summary="Ticket volume forecast")
def ticket_volume_forecast(
    org_id: str = Query(...),
    days: int = Query(30, ge=7, le=180),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return APIResponse.ok(data=predict_ticket_volume(db, org_id, days_ahead=days))


@router.get("/agents", summary="Per-agent load forecast")
def agent_load_forecast(
    org_id: str = Query(...),
    days: int = Query(14, ge=7, le=90),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return APIResponse.ok(data=predict_agent_load(db, org_id, days_ahead=days))


@router.get("/recommendations", summary="Staffing capacity recommendations")
def capacity_recommendations(
    org_id: str = Query(...),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return APIResponse.ok(data=get_capacity_recommendations(db, org_id))


@router.get("/burnout-risk", summary="Agent burnout risk assessment")
def burnout_risk(
    user_id: str = Query(...),
    org_id: str = Query(...),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return APIResponse.ok(data=calculate_burnout_risk(db, user_id, org_id))


@router.get("/config", summary="Get capacity planning config")
def get_config(
    org_id: str = Query(...),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return APIResponse.ok(data=get_capacity_config(db, org_id))


@router.put("/config", summary="Update capacity planning config")
def update_config(
    body: dict,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: configuracion: la forma de la ruta manda sobre el fichero
):
    org_id = body.get("org_id", "default")
    return APIResponse.ok(data=save_capacity_config(db, org_id, body))
