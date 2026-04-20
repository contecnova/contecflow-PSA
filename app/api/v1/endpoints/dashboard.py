from fastapi import APIRouter, Depends, Body
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import date

from app.db.session import get_db
from app.core.deps import get_current_user, require_admin, require_any_manager
from app.models.user import User
from app.schemas import DashboardKPIs, ProjectHealthItem, ResourceLoadItem
from app.services.dashboard_service import (
    get_global_kpis,
    get_projects_health as svc_get_projects_health,
    get_resource_load,
    get_profitability,
    get_team_productivity,
)

router = APIRouter()


@router.get("/kpis", response_model=DashboardKPIs, summary="KPIs globales para dirección")
def get_kpis(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return get_global_kpis(db, current_user)


@router.get("/projects-health", response_model=List[ProjectHealthItem], summary="Salud de todos los proyectos")
def projects_health_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return svc_get_projects_health(db, current_user)


@router.get("/resource-load", response_model=List[ResourceLoadItem], summary="Carga detallada por recurso")
def get_resource_load_endpoint(
    week_start: Optional[date] = None,
    department: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return get_resource_load(week_start, department, db, current_user)


@router.get("/profitability", summary="Rentabilidad por proyecto (solo admin)")
def get_profitability_endpoint(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return get_profitability(date_from, date_to, db, current_user)


@router.get("/productivity/team", summary="Productividad del equipo completo")
def get_team_productivity_endpoint(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    department: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return get_team_productivity(date_from, date_to, department, db, current_user)


# ── Dashboard seed por rol ────────────────────────────────────────────────────

ROLE_DASHBOARD_SEEDS = {
    "admin": {
        "visible": ["kpis", "health", "team", "pipeline", "clients", "alerts", "hours", "activity", "tasks", "docs"],
        "order":   ["kpis", "health", "team", "pipeline", "clients", "alerts", "hours", "activity", "tasks", "docs"],
    },
    "pm": {
        "visible": ["kpis", "health", "tasks", "team", "hours", "activity", "alerts", "docs"],
        "order":   ["kpis", "health", "tasks", "team", "hours", "activity", "alerts", "docs"],
    },
    "hr": {
        "visible": ["team", "hours", "activity", "tasks"],
        "order":   ["team", "hours", "activity", "tasks"],
    },
    "employee": {
        "visible": ["tasks", "hours", "activity"],
        "order":   ["tasks", "hours", "activity"],
    },
    "team_lead": {
        "visible": ["kpis", "tasks", "team", "hours", "alerts", "activity"],
        "order":   ["kpis", "tasks", "team", "hours", "alerts", "activity"],
    },
}

@router.get("/seed-config")
def get_dashboard_seed(current_user: User = Depends(get_current_user)):
    role = getattr(current_user, "role", "employee")
    if hasattr(role, "value"):
        role = role.value
    seed = ROLE_DASHBOARD_SEEDS.get(role) or ROLE_DASHBOARD_SEEDS["employee"]
    return {"role": role, "config": seed}


_dashboard_widgets: list = []

@router.post("/widgets", summary="Add dashboard widget", status_code=201)
def add_dashboard_widget(
    payload: dict = Body(...),
    current_user: User = Depends(get_current_user),
):
    widget = {"id": len(_dashboard_widgets) + 1, **payload}
    _dashboard_widgets.append(widget)
    return widget


@router.patch("/widgets/reorder", summary="Reorder dashboard widgets")
def reorder_dashboard_widgets(
    payload: dict = Body(...),
    current_user: User = Depends(get_current_user),
):
    return {"ok": True, "order": payload.get("order", [])}
