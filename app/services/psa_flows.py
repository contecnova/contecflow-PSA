from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.models.financial import CapacityPlan, Timesheet, TimesheetStatus
from app.models.imputation import Imputation
from app.models.project import Project
from app.models.resources import Absence, AbsenceStatus
from app.models.sprints import Sprint, SprintStatus, SprintTask
from app.models.user import User, UserRole


def approve_imputation_flow(db: Session, imputation_id: str, current_user: User) -> Imputation:
    imp = db.query(Imputation).filter(Imputation.id == imputation_id).first()
    if not imp:
        raise HTTPException(status_code=404, detail="Imputacion no encontrada")

    if current_user.role not in [UserRole.admin, UserRole.hr]:
        if not imp.project_id:
            raise HTTPException(status_code=403, detail="No tienes permiso para aprobar esta imputacion")
        project = db.query(Project).filter(Project.id == imp.project_id).first()
        if not project or project.pm_id != current_user.id:
            raise HTTPException(status_code=403, detail="No tienes permiso para aprobar esta imputacion")

    imp.is_approved = True
    imp.approved_by = current_user.id
    imp.approved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(imp)
    return imp


def review_timesheet_flow(
    db: Session,
    timesheet_id: str,
    current_user: User,
    approved: bool,
    notes: Optional[str],
) -> Timesheet:
    ts = db.query(Timesheet).filter(Timesheet.id == timesheet_id).first()
    if not ts:
        raise HTTPException(status_code=404, detail="Timesheet no encontrado")
    if ts.status != TimesheetStatus.submitted:
        raise HTTPException(status_code=400, detail="Solo se pueden revisar timesheets enviados")

    ts.status = TimesheetStatus.approved if approved else TimesheetStatus.rejected
    ts.reviewed_by = current_user.id
    ts.reviewed_at = datetime.now(timezone.utc)
    ts.review_notes = notes

    if approved:
        week_end = ts.week_start + timedelta(days=6)
        db.query(Imputation).filter(
            Imputation.user_id == ts.user_id,
            Imputation.date >= ts.week_start,
            Imputation.date <= week_end,
        ).update(
            {
                "is_approved": True,
                "approved_by": current_user.id,
                "approved_at": datetime.now(timezone.utc),
            }
        )

    db.commit()
    db.refresh(ts)
    return ts


def sync_timesheet_from_imputations_flow(db: Session, user_id: str, week_start: date) -> Timesheet:
    week_end = week_start + timedelta(days=6)

    ts = db.query(Timesheet).filter(
        Timesheet.user_id == user_id,
        Timesheet.week_start == week_start,
    ).first()

    imps = db.query(Imputation).filter(
        Imputation.user_id == user_id,
        Imputation.date >= week_start,
        Imputation.date <= week_end,
    ).all()

    total = sum(i.hours for i in imps)
    billable = sum(i.hours for i in imps if i.is_billable)
    cost = sum(i.cost_amount or 0 for i in imps)

    if not ts:
        ts = Timesheet(
            user_id=user_id,
            week_start=week_start,
            week_end=week_end,
            total_hours=total,
            billable_hours=billable,
            total_cost=cost,
        )
        db.add(ts)
    elif ts.status in [TimesheetStatus.draft, TimesheetStatus.rejected]:
        ts.total_hours = total
        ts.billable_hours = billable
        ts.total_cost = cost

    db.commit()
    db.refresh(ts)
    return ts


def submit_timesheet_flow(db: Session, user_id: str, week_start: date) -> Timesheet:
    ts = sync_timesheet_from_imputations_flow(db, user_id, week_start)
    if ts.status not in [TimesheetStatus.draft, TimesheetStatus.rejected]:
        raise HTTPException(status_code=400, detail="Solo se pueden enviar timesheets en borrador o rechazados")
    if ts.total_hours == 0:
        raise HTTPException(status_code=400, detail="No puedes enviar un timesheet vacío")

    ts.status = TimesheetStatus.submitted
    ts.submitted_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(ts)
    return ts


def send_back_timesheet_flow(db: Session, timesheet_id: str, current_user: User, notes: str = "") -> Timesheet:
    ts = db.query(Timesheet).filter(Timesheet.id == timesheet_id).first()
    if not ts:
        raise HTTPException(status_code=404, detail="Timesheet no encontrado")
    if ts.status != TimesheetStatus.submitted:
        raise HTTPException(status_code=400, detail="Solo se pueden devolver timesheets en estado enviado")

    ts.status = TimesheetStatus.rejected
    ts.reviewed_by = current_user.id
    ts.reviewed_at = datetime.now(timezone.utc)
    note_prefix = "[Devuelto para correccion]"
    ts.review_notes = f"{note_prefix} {notes}".strip()

    db.commit()
    db.refresh(ts)
    return ts


def build_invoice_preview_from_timesheets_flow(
    db: Session,
    project_id: str,
    date_from: Optional[date],
    date_to: Optional[date],
    tax_rate: Optional[float],
) -> dict:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")

    imps_q = db.query(Imputation).options(joinedload(Imputation.user)).filter(
        Imputation.project_id == project_id,
        Imputation.is_billable == True,
        Imputation.is_approved == True,
        Imputation.is_invoiced != True,
    )
    if date_from:
        imps_q = imps_q.filter(Imputation.date >= date_from)
    if date_to:
        imps_q = imps_q.filter(Imputation.date <= date_to)
    imps = imps_q.all()

    by_profile = {}
    for imp in imps:
        rate = project.billing_rate or (imp.user.hourly_rate if imp.user else 0) or 0
        profile = imp.user.job_title or imp.user.role if imp.user else "Consultor"
        key = f"{profile}___{rate}"
        if key not in by_profile:
            by_profile[key] = {
                "description": f"{profile} ({rate}EUR/h)",
                "hours": 0,
                "rate": rate,
                "ids": [],
            }
        by_profile[key]["hours"] += imp.hours
        by_profile[key]["ids"].append(imp.id)

    lines = []
    subtotal = 0.0
    for i, data in enumerate(by_profile.values()):
        amount = round(data["hours"] * data["rate"], 2)
        subtotal += amount
        lines.append(
            {
                "order": i,
                "description": data["description"],
                "quantity": round(data["hours"], 2),
                "unit": "h",
                "unit_price": data["rate"],
                "discount_pct": 0,
                "amount": amount,
                "source_type": "timesheet",
                "source_ids": json.dumps(data["ids"]),
            }
        )

    safe_tax_rate = tax_rate if tax_rate is not None else settings.DEFAULT_TAX_RATE
    tax_amount = round(subtotal * safe_tax_rate / 100, 2)
    total = round(subtotal + tax_amount, 2)

    return {
        "preview": True,
        "project_name": project.name,
        "client_name": project.client_name,
        "period_from": str(date_from) if date_from else None,
        "period_to": str(date_to) if date_to else None,
        "lines": lines,
        "subtotal": round(subtotal, 2),
        "tax_rate": safe_tax_rate,
        "tax_amount": tax_amount,
        "total": total,
        "currency": project.currency or settings.DEFAULT_CURRENCY,
        "imputation_count": len(imps),
    }


def close_sprint_flow(db: Session, project_id: str, sprint_id: str) -> dict:
    sprint = (
        db.query(Sprint)
        .options(joinedload(Sprint.sprint_tasks).joinedload(SprintTask.task))
        .filter(Sprint.id == sprint_id, Sprint.project_id == project_id)
        .first()
    )
    if not sprint:
        raise HTTPException(status_code=404, detail="Sprint no encontrado")

    sprint.status = SprintStatus.completed
    sprint.closed_at = datetime.now(timezone.utc)
    if not sprint.end_date:
        sprint.end_date = date.today()

    sprint.completed_points = sum(
        st.task.story_points or 0
        for st in sprint.sprint_tasks
        if st.task and st.task.status == "done"
    )
    duration_weeks = max((sprint.end_date - sprint.start_date).days / 7, 0.5) if sprint.start_date else 1
    sprint.velocity = round(sprint.completed_points / duration_weeks, 1)

    incomplete = [st for st in sprint.sprint_tasks if st.task and st.task.status != "done"]
    for st in incomplete:
        db.delete(st)

    db.commit()
    return {
        "ok": True,
        "completed_points": sprint.completed_points,
        "velocity": sprint.velocity,
        "incomplete_tasks": len(incomplete),
    }


def create_capacity_plan_flow(
    db: Session,
    current_user: User,
    user_id: str,
    week_start: date,
    new_hours: float,
    project_id: Optional[str],
    notes: Optional[str],
) -> CapacityPlan:
    existing_hours = (
        db.query(func.sum(CapacityPlan.planned_hours))
        .filter(CapacityPlan.user_id == user_id, CapacityPlan.week_start == week_start)
        .scalar()
        or 0.0
    )
    user_obj = db.query(User).filter(User.id == user_id).first()
    weekly_capacity = getattr(user_obj, "weekly_capacity_hours", None) or settings.DEFAULT_WEEKLY_CAPACITY_HOURS
    if existing_hours + new_hours > weekly_capacity:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Sobreasignacion: el usuario ya tiene {existing_hours}h planificadas esta semana "
                f"y anadir {new_hours}h supera la capacidad de {weekly_capacity}h."
            ),
        )

    week_end = week_start + timedelta(days=6)
    conflict = db.query(Absence).filter(
        Absence.user_id == user_id,
        Absence.status == AbsenceStatus.approved,
        Absence.start_date <= week_end,
        Absence.end_date >= week_start,
    ).first()
    if conflict:
        raise HTTPException(
            status_code=409,
            detail=(
                "Conflicto de ausencia: el usuario tiene una ausencia aprobada del "
                f"{conflict.start_date} al {conflict.end_date}."
            ),
        )

    plan = CapacityPlan(
        user_id=user_id,
        project_id=project_id,
        week_start=week_start,
        planned_hours=new_hours,
        notes=notes,
        created_by=current_user.id,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan
