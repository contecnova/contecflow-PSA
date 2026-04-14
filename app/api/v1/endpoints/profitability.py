from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from typing import Optional
from datetime import date, timedelta
from pydantic import BaseModel

from app.db.session import get_db
from app.core.deps import get_current_user, require_admin
from app.models.user import User, UserRole
from app.models.project import Project, ProjectStatus
from app.models.task import TaskStatus
from app.models.imputation import Imputation
from app.models.financial import ProjectMilestone

router = APIRouter()


class MilestoneIn(BaseModel):
    name: str
    description: Optional[str] = None
    due_date: Optional[date] = None
    billing_amount: Optional[float] = None
    billing_pct: Optional[float] = None
    sort_order: int = 0

class MilestoneOut(MilestoneIn):
    id: str
    project_id: str
    is_completed: bool
    completed_date: Optional[date] = None
    is_billed: bool
    billed_at: Optional[date] = None
    model_config = {"from_attributes": True}

class MilestoneUpdate(BaseModel):
    is_completed: Optional[bool] = None
    completed_date: Optional[date] = None
    is_billed: Optional[bool] = None
    billed_at: Optional[date] = None
    name: Optional[str] = None
    due_date: Optional[date] = None
    billing_amount: Optional[float] = None


def _calc_project_profitability(project: Project, db: Session) -> dict:
    """Calculate full P&L for a project."""
    imps = db.query(Imputation).filter(
        Imputation.project_id == project.id
    ).all()

    total_hours = sum(i.hours for i in imps)
    billable_hours = sum(i.hours for i in imps if i.is_billable)
    internal_cost = sum(i.cost_amount or 0 for i in imps)

    # Revenue from billing rate × billable hours
    billing_revenue = 0
    if project.billing_rate and billable_hours:
        billing_revenue = project.billing_rate * billable_hours
    elif project.contract_amount:
        # For fixed price, use contract amount × progress
        milestones = db.query(ProjectMilestone).filter(
            ProjectMilestone.project_id == project.id,
            ProjectMilestone.is_billed == True,
        ).all()
        billing_revenue = sum(m.billing_amount or 0 for m in milestones)

    gross_margin = billing_revenue - internal_cost
    margin_pct = (gross_margin / billing_revenue * 100) if billing_revenue > 0 else 0

    # Budget consumption
    budget_used_pct = 0
    if project.budget_amount and project.budget_amount > 0:
        budget_used_pct = (internal_cost / project.budget_amount) * 100

    # Forecast at completion
    tasks = project.tasks if hasattr(project, 'tasks') else []
    progress = 0
    if tasks:
        weighted_done = 0.0
        for t in tasks:
            if t.status == TaskStatus.done:
                weighted_done += 1.0
            elif t.status == TaskStatus.in_progress:
                weighted_done += 0.5
            elif t.status == TaskStatus.review:
                weighted_done += 0.8
            elif t.status in [TaskStatus.todo, TaskStatus.backlog, TaskStatus.blocked, TaskStatus.cancelled]:
                weighted_done += 0.0
        progress = (weighted_done / len(tasks)) * 100 if tasks else 0

    forecast_cost = 0
    if progress >= 5.0:
        # Only extrapolate when ≥5% complete — avoids absurd multipliers at near-zero progress
        remaining_pct = 100 - progress
        forecast_cost = round(internal_cost + (internal_cost * remaining_pct / progress), 2)
    elif total_hours > 0 and project.budget_hours:
        forecast_cost = round((internal_cost / total_hours) * project.budget_hours, 2)

    # ── EVM (Earned Value Management) ─────────────────────────────────────────
    # Planned Value (PV): cuánto debería haberse gastado según el plan temporal
    # Se basa en el tiempo transcurrido respecto a la duración total del proyecto
    today = date.today()
    if project.start_date and project.end_date_planned and project.end_date_planned > project.start_date:
        total_days = (project.end_date_planned - project.start_date).days
        elapsed_days = max(0, (today - project.start_date).days)
        planned_pct = min(100, (elapsed_days / total_days) * 100)
    else:
        planned_pct = None  # No schedule data — PV/SPI cannot be computed reliably
    pv  = round((project.budget_amount or 0) * planned_pct / 100, 2) if planned_pct is not None else None
    # Earned Value (EV): valor ganado real
    ev  = round((project.budget_amount or 0) * progress / 100, 2) if progress > 0 else 0
    # Actual Cost (AC)
    ac  = round(internal_cost, 2)

    # Índices de rendimiento
    cpi = round(ev / ac, 3)  if ac  > 0 else None  # Cost Performance Index (>1 = bajo coste)
    spi = round(ev / pv, 3)  if (pv is not None and pv > 0) else None  # Schedule Performance Index (>1 = adelantado)

    # EAC (Estimate at Completion): coste total estimado al finalizar
    budget_at_completion = project.budget_amount or forecast_cost or 0
    if cpi and cpi > 0:
        eac = round(ac + (budget_at_completion - ev) / cpi, 2)
    elif progress >= 1.0:  # guard: avoid division by near-zero (would produce astronomical EAC)
        eac = round(ac / (progress / 100), 2)
    else:
        eac = budget_at_completion

    # ETC (Estimate to Complete): coste restante estimado
    etc = round(max(eac - ac, 0), 2)

    # VAC (Variance at Completion): desviación total estimada
    vac = round(budget_at_completion - eac, 2)

    # CV (Cost Variance) y SV (Schedule Variance)
    cv  = round(ev - ac, 2)
    sv  = round(ev - pv, 2)   if pv is not None else None

    # Alerta de riesgo
    margin_at_completion = 0
    if billing_revenue > 0 and eac > 0:
        margin_at_completion = round((billing_revenue - eac) / billing_revenue * 100, 1)

    risk_flag = (
        "critical" if (cpi and cpi < 0.8) or margin_at_completion < 0 else
        "warning"  if (cpi and cpi < 0.95) or margin_at_completion < 10 else
        "ok"
    )

    return {
        "project_id": project.id,
        "project_code": project.code,
        "project_name": project.name,
        "client_name": project.client_name,
        "department": project.department,
        "status": project.status,
        "billing_type": project.billing_type or "time_material",
        "is_billable": project.is_billable,
        # Hours
        "total_hours": round(total_hours, 1),
        "billable_hours": round(billable_hours, 1),
        "budget_hours": project.budget_hours,
        "hours_used_pct": round((total_hours / project.budget_hours * 100), 1) if project.budget_hours else None,
        # Money
        "internal_cost": round(internal_cost, 2),
        "billing_revenue": round(billing_revenue, 2),
        "gross_margin": round(gross_margin, 2),
        "margin_pct": round(margin_pct, 1),
        "budget_amount": project.budget_amount,
        "contract_amount": project.contract_amount,
        "budget_used_pct": round(budget_used_pct, 1),
        "forecast_cost": round(forecast_cost, 2),
        # Rates
        "billing_rate": project.billing_rate,
        "avg_cost_rate": round(internal_cost / total_hours, 2) if total_hours > 0 else 0,
        # EVM — Earned Value Management
        "progress_pct":   round(progress, 1),
        "pv":             pv,    # Planned Value (None when no project dates)
        "ev":             ev,    # Earned Value
        "ac":             ac,    # Actual Cost
        "cpi":            cpi,   # Cost Performance Index
        "spi":            spi,   # Schedule Performance Index (None when no project dates)
        "cv":             cv,    # Cost Variance
        "sv":             sv,    # Schedule Variance (None when no project dates)
        "evm_no_schedule": planned_pct is None,
        "eac":            eac,   # Estimate at Completion
        "etc":            etc,   # Estimate to Complete
        "vac":            vac,   # Variance at Completion
        "margin_at_completion": margin_at_completion,
        "risk_flag":      risk_flag,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/summary", summary="Rentabilidad de todos los proyectos")
def get_profitability_summary(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    q = db.query(Project).options(joinedload(Project.tasks))
    if status:
        q = q.filter(Project.status == status)
    else:
        q = q.filter(Project.status.in_([ProjectStatus.active, ProjectStatus.closed]))

    projects = q.all()
    results = [_calc_project_profitability(p, db) for p in projects]

    # Portfolio totals
    total_revenue = sum(r["billing_revenue"] for r in results)
    total_cost = sum(r["internal_cost"] for r in results)
    total_margin = total_revenue - total_cost
    portfolio_margin_pct = (total_margin / total_revenue * 100) if total_revenue > 0 else 0

    return {
        "projects": sorted(results, key=lambda x: x["gross_margin"]),
        "portfolio": {
            "total_revenue": round(total_revenue, 2),
            "total_cost": round(total_cost, 2),
            "total_margin": round(total_margin, 2),
            "margin_pct": round(portfolio_margin_pct, 1),
            "project_count": len(results),
            "billable_projects": sum(1 for r in results if r["is_billable"]),
        }
    }


@router.get("/{project_id}", summary="Rentabilidad detallada de un proyecto")
def get_project_profitability(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in [UserRole.admin, UserRole.pm]:
        raise HTTPException(403, "Acceso denegado")

    project = db.query(Project).options(
        joinedload(Project.tasks),
        joinedload(Project.project_manager),
    ).filter(Project.id == project_id).first()

    if not project:
        raise HTTPException(404, "Proyecto no encontrado")

    base = _calc_project_profitability(project, db)

    # By person breakdown
    by_person = db.query(
        Imputation.user_id,
        User.full_name,
        func.sum(Imputation.hours).label("hours"),
        func.sum(Imputation.cost_amount).label("cost"),
    ).join(User, User.id == Imputation.user_id).filter(
        Imputation.project_id == project_id
    ).group_by(Imputation.user_id, User.full_name).all()

    # By week breakdown
    by_week = db.query(
        Imputation.date,
        func.sum(Imputation.hours).label("hours"),
        func.sum(Imputation.cost_amount).label("cost"),
    ).filter(
        Imputation.project_id == project_id
    ).group_by(Imputation.date).order_by(Imputation.date).all()

    # Weekly aggregation
    weekly = {}
    for row in by_week:
        d = row.date if isinstance(row.date, date) else row[0]
        if isinstance(d, str):
            d = date.fromisoformat(d)
        ws = d - timedelta(days=d.weekday())
        key = str(ws)
        if key not in weekly:
            weekly[key] = {"week": key, "hours": 0, "cost": 0}
        weekly[key]["hours"] += row.hours or 0
        weekly[key]["cost"] += row.cost or 0

    # Milestones
    milestones = db.query(ProjectMilestone).filter(
        ProjectMilestone.project_id == project_id
    ).order_by(ProjectMilestone.sort_order).all()

    base["by_person"] = [{
        "user_id": r.user_id,
        "user_name": r.full_name,
        "hours": round(r.hours or 0, 1),
        "cost": round(r.cost or 0, 2),
        "billing": round((r.hours or 0) * (project.billing_rate or 0), 2),
    } for r in by_person]

    base["by_week"] = sorted(weekly.values(), key=lambda x: x["week"])

    base["milestones"] = [{
        "id": m.id,
        "name": m.name,
        "due_date": str(m.due_date) if m.due_date else None,
        "completed_date": str(m.completed_date) if m.completed_date else None,
        "billing_amount": m.billing_amount,
        "billing_pct": m.billing_pct,
        "is_completed": m.is_completed,
        "is_billed": m.is_billed,
        "billed_at": str(m.billed_at) if m.billed_at else None,
    } for m in milestones]

    return base


# ── Milestones ────────────────────────────────────────────────────────────────

@router.get("/{project_id}/milestones", summary="Hitos de un proyecto")
def get_milestones(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    milestones = db.query(ProjectMilestone).filter(
        ProjectMilestone.project_id == project_id
    ).order_by(ProjectMilestone.sort_order).all()
    return [{"id": m.id, "name": m.name, "description": m.description,
             "due_date": str(m.due_date) if m.due_date else None,
             "completed_date": str(m.completed_date) if m.completed_date else None,
             "billing_amount": m.billing_amount, "billing_pct": m.billing_pct,
             "is_billed": m.is_billed, "billed_at": str(m.billed_at) if m.billed_at else None,
             "is_completed": m.is_completed, "sort_order": m.sort_order} for m in milestones]


@router.post("/{project_id}/milestones", summary="Crear hito")
def create_milestone(
    project_id: str,
    payload: MilestoneIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in [UserRole.admin, UserRole.pm]:
        raise HTTPException(403, "Acceso denegado")
    m = ProjectMilestone(project_id=project_id, **payload.model_dump())
    db.add(m); db.commit(); db.refresh(m)
    return m


@router.patch("/{project_id}/milestones/{milestone_id}", summary="Actualizar hito")
def update_milestone(
    project_id: str,
    milestone_id: str,
    payload: MilestoneUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in [UserRole.admin, UserRole.pm]:
        raise HTTPException(403, "Acceso denegado")
    m = db.query(ProjectMilestone).filter(
        ProjectMilestone.id == milestone_id,
        ProjectMilestone.project_id == project_id,
    ).first()
    if not m:
        raise HTTPException(404, "Hito no encontrado")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(m, k, v)
    db.commit(); db.refresh(m)
    return m


@router.delete("/{project_id}/milestones/{milestone_id}", summary="Eliminar hito")
def delete_milestone(
    project_id: str,
    milestone_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in [UserRole.admin, UserRole.pm]:
        raise HTTPException(403, "Acceso denegado")
    m = db.query(ProjectMilestone).filter(ProjectMilestone.id == milestone_id, ProjectMilestone.project_id == project_id).first()
    if not m:
        raise HTTPException(404, "Hito no encontrado")
    db.delete(m); db.commit()
    return {"ok": True}
