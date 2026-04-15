from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import date

from app.db.session import get_db
from app.core.deps import get_current_user, require_admin, require_any_manager
from app.models.user import User
from app.schemas.schemas import DashboardKPIs, ProjectHealthItem, ResourceLoadItem
from app.services.dashboard_service import (
    get_global_kpis,
    get_projects_health,
    get_resource_load,
    get_profitability,
    get_team_productivity,
)

router = APIRouter()


@router.get("/kpis", response_model=DashboardKPIs, summary="KPIs globales para dirección")
def get_kpis(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return get_global_kpis(db)


@router.get("/projects-health", response_model=List[ProjectHealthItem], summary="Salud de todos los proyectos")
def get_projects_health(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    projects = db.query(Project).filter(Project.status == ProjectStatus.active).all()
    if not projects:
        return []

    project_ids = [p.id for p in projects]

    # ── Batch queries (eliminan el N+1 original) ─────────────────────────────
    # Coste total por proyecto
    cost_rows = db.query(
        Imputation.project_id,
        func.sum(Imputation.cost_amount).label("total_cost"),
    ).filter(Imputation.project_id.in_(project_ids)).group_by(Imputation.project_id).all()
    cost_by_pid = {r.project_id: float(r.total_cost or 0) for r in cost_rows}

    # Total de tareas por proyecto
    task_total_rows = db.query(
        Task.project_id,
        func.count(Task.id).label("cnt"),
    ).filter(Task.project_id.in_(project_ids)).group_by(Task.project_id).all()
    task_total_by_pid = {r.project_id: r.cnt for r in task_total_rows}

    # Tareas done por proyecto
    task_done_rows = db.query(
        Task.project_id,
        func.count(Task.id).label("cnt"),
    ).filter(
        Task.project_id.in_(project_ids),
        Task.status == TaskStatus.done,
    ).group_by(Task.project_id).all()
    task_done_by_pid = {r.project_id: r.cnt for r in task_done_rows}

    # Tamaño del equipo por proyecto (usuarios distintos con imputaciones)
    team_rows = db.query(
        Imputation.project_id,
        func.count(func.distinct(Imputation.user_id)).label("cnt"),
    ).filter(Imputation.project_id.in_(project_ids)).group_by(Imputation.project_id).all()
    team_by_pid = {r.project_id: r.cnt for r in team_rows}

    # Alertas abiertas por proyecto
    alert_rows = db.query(
        Alert.project_id,
        func.count(Alert.id).label("cnt"),
    ).filter(
        Alert.project_id.in_(project_ids),
        Alert.is_resolved == False,
    ).group_by(Alert.project_id).all()
    alert_by_pid = {r.project_id: r.cnt for r in alert_rows}

    today = date.today()
    result = []
    for p in projects:
        total_cost    = cost_by_pid.get(p.id, 0.0)
        tasks_total   = task_total_by_pid.get(p.id, 0)
        tasks_done    = task_done_by_pid.get(p.id, 0)
        team_size     = team_by_pid.get(p.id, 0)
        alerts_count  = alert_by_pid.get(p.id, 0)
        progress_pct  = round((tasks_done / tasks_total) * 100, 1) if tasks_total > 0 else 0.0

        budget_used_pct = 0.0
        if p.budget_amount and p.budget_amount > 0:
            budget_used_pct = round((total_cost / p.budget_amount) * 100, 1)

        deviation_days = 0
        if p.end_date_planned and today > p.end_date_planned:
            deviation_days = (today - p.end_date_planned).days

        # ── Composite health score 0-100 ──────────────────────────────────
        score = 100
        # Budget penalty
        if budget_used_pct > 100:
            score -= min(30, int(budget_used_pct - 80))
        elif budget_used_pct > 80:
            score -= int((budget_used_pct - 80) * 0.8)
        # Schedule penalty
        if deviation_days > 30:
            score -= 25
        elif deviation_days > 14:
            score -= 15
        elif deviation_days > 7:
            score -= 10
        elif deviation_days > 0:
            score -= 5
        # Alerts penalty (capped at 20)
        score -= min(20, alerts_count * 5)
        # Risk level penalty
        score -= {"critical": 15, "high": 8, "medium": 3, "low": 0}.get(p.risk_level.value, 0)
        # Small progress bonus if mostly done
        if progress_pct >= 80:
            score += 5
        health_score = max(0, min(100, score))

        result.append(ProjectHealthItem(
            project_id=p.id,
            project_name=p.name,
            project_code=p.code,
            budget_used_pct=budget_used_pct,
            schedule_deviation_days=deviation_days,
            risk_level=p.risk_level.value,
            status=p.status.value,
            team_size=team_size,
            alerts_count=alerts_count,
            tasks_total=tasks_total,
            tasks_done=tasks_done,
            progress_pct=progress_pct,
            health_score=health_score,
        ))

    return result


@router.get("/resource-load", response_model=List[ResourceLoadItem], summary="Carga detallada por recurso")
def get_resource_load_endpoint(
    week_start: Optional[date] = None,
    department: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return get_resource_load(week_start, department, db)


@router.get("/profitability", summary="Rentabilidad por proyecto (solo admin)")
def get_profitability_endpoint(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return get_profitability(date_from, date_to, db)


@router.get("/productivity/team", summary="Productividad del equipo completo")
def get_team_productivity_endpoint(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    department: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return get_team_productivity(date_from, date_to, department, db)


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
