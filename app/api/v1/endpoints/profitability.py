from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date, timedelta

from app.db.session import get_db
from app.core.deps import get_current_user, require_admin
from app.models.user import User, UserRole
from app.services import profitability_service
from app.schemas.milestones import MilestoneIn, MilestoneUpdate

router = APIRouter()


@router.get("/summary", summary="Rentabilidad de todos los proyectos")
def get_profitability_summary(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
    response: Response = None,
):
    projects = profitability_service.get_summary_projects(db, status)
    project_ids = [p.id for p in projects]

    imputation_totals_by_project = profitability_service.get_imputation_totals_by_project(db, project_ids)
    billed_milestones_by_project = profitability_service.get_billed_milestones_total_by_project(db, project_ids)

    results = [
        profitability_service.calc_project_profitability(
            p,
            db,
            imputation_totals=imputation_totals_by_project.get(p.id, {}),
            billed_milestones_total=billed_milestones_by_project.get(p.id, 0),
        )
        for p in projects
    ]

    total_revenue = sum(r["billing_revenue"] for r in results)
    total_cost = sum(r["internal_cost"] for r in results)
    total_margin = total_revenue - total_cost
    portfolio_margin_pct = (total_margin / total_revenue * 100) if total_revenue > 0 else 0

    if response is not None:
        response.headers["x-api-version"] = "1"
        response.headers["x-api-deprecated"] = "true"
        response.headers["deprecation"] = "true"

    return {
        "projects": sorted(results, key=lambda x: x["gross_margin"]),
        "portfolio": {
            "total_revenue": round(total_revenue, 2),
            "total_cost": round(total_cost, 2),
            "total_margin": round(total_margin, 2),
            "margin_pct": round(portfolio_margin_pct, 1),
            "project_count": len(results),
            "billable_projects": sum(1 for r in results if r["is_billable"]),
        },
    }


@router.get("/projects", summary="Lista de proyectos con datos de rentabilidad (para dashboards)")
def get_profitability_projects(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    response: Response = None,
):
    """Returns a flat list of projects with profitability metrics (margin_pct, revenue, cost, etc.)."""
    if response is not None:
        response.headers["x-api-version"] = "1"
        response.headers["x-api-deprecated"] = "true"
        response.headers["deprecation"] = "true"
    projects = profitability_service.get_summary_projects(db, status)
    project_ids = [p.id for p in projects]

    imputation_totals_by_project = profitability_service.get_imputation_totals_by_project(db, project_ids)
    billed_milestones_by_project = profitability_service.get_billed_milestones_total_by_project(db, project_ids)

    results = [
        profitability_service.calc_project_profitability(
            p,
            db,
            imputation_totals=imputation_totals_by_project.get(p.id, {}),
            billed_milestones_total=billed_milestones_by_project.get(p.id, 0),
        )
        for p in projects
    ]

    return sorted(results, key=lambda x: -(x.get("gross_margin") or 0))


@router.get("/{project_id}", summary="Rentabilidad detallada de un proyecto")
def get_project_profitability(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    response: Response = None,
):
    if response is not None:
        response.headers["x-api-version"] = "1"
        response.headers["x-api-deprecated"] = "true"
        response.headers["deprecation"] = "true"
    if current_user.role not in [UserRole.admin, UserRole.pm]:
        raise HTTPException(403, "Acceso denegado")

    project = profitability_service.get_project_with_tasks(db, project_id)
    if not project:
        raise HTTPException(404, "Proyecto no encontrado")

    base = profitability_service.calc_project_profitability(project, db)

    by_person = profitability_service.get_imputations_by_person(db, project_id)
    by_day_rows = profitability_service.get_imputations_by_day(db, project_id)

    weekly: dict = {}
    for row in by_day_rows:
        d = row.date if hasattr(row, 'date') else row[0]
        if isinstance(d, str):
            d = date.fromisoformat(d)
        ws = d - timedelta(days=d.weekday())
        key = str(ws)
        if key not in weekly:
            weekly[key] = {"week": key, "hours": 0, "cost": 0}
        weekly[key]["hours"] += getattr(row, 'hours', 0) or 0
        weekly[key]["cost"] += getattr(row, 'cost', 0) or 0

    milestones = profitability_service.list_milestones(db, project_id)

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
    response: Response = None,
):
    if response is not None:
        response.headers["x-api-version"] = "1"
        response.headers["x-api-deprecated"] = "true"
        response.headers["deprecation"] = "true"
    milestones = profitability_service.list_milestones(db, project_id)
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
    return profitability_service.create_milestone(db, project_id, payload.model_dump())


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
    m = profitability_service.get_milestone(db, milestone_id, project_id)
    if not m:
        raise HTTPException(404, "Hito no encontrado")
    return profitability_service.update_milestone(db, m, payload.model_dump(exclude_unset=True))


@router.delete("/{project_id}/milestones/{milestone_id}", summary="Eliminar hito")
def delete_milestone(
    project_id: str,
    milestone_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in [UserRole.admin, UserRole.pm]:
        raise HTTPException(403, "Acceso denegado")
    m = profitability_service.get_milestone(db, milestone_id, project_id)
    if not m:
        raise HTTPException(404, "Hito no encontrado")
    profitability_service.delete_milestone(db, m)
    return {"ok": True}
