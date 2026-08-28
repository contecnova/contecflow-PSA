"""
timesheet_service.py — Funciones de servicio para gestión de timesheets.
"""
from sqlalchemy.orm import Session, joinedload
from typing import Optional
from datetime import date, timedelta

from app.models.financial import Timesheet, TimesheetStatus
from app.models.imputation import Imputation
from app.core import timeutil


def get_timesheet_lines(db: Session, user_id: str, week_start: date) -> list:
    """Devuelve las líneas (imputaciones) de un timesheet para la semana dada."""
    week_end = week_start + timedelta(days=6)
    imputations = (
        db.query(Imputation)
        .options(joinedload(Imputation.project), joinedload(Imputation.task))
        .filter(
            Imputation.user_id == user_id,
            Imputation.date >= week_start,
            Imputation.date <= week_end,
        )
        .order_by(Imputation.date)
        .all()
    )
    return [
        {
            "id": imp.id,
            "date": str(imp.date),
            "hours": imp.hours,
            "project_id": imp.project_id,
            "project_name": imp.project.name if imp.project else None,
            "task_id": imp.task_id,
            "task_title": imp.task.title if imp.task else None,
            "description": imp.description,
            "billable": imp.is_billable,
        }
        for imp in imputations
    ]


def list_pending_timesheets(db: Session) -> list:
    """Devuelve todos los timesheets pendientes de revisión."""
    timesheets = (
        db.query(Timesheet)
        .options(joinedload(Timesheet.user))
        .filter(Timesheet.status == TimesheetStatus.submitted)
        .order_by(Timesheet.week_start.desc())
        .all()
    )
    return _enrich(timesheets)


def list_team_timesheets(
    db: Session,
    week_start: Optional[date],
    user_id: Optional[str],
    status: Optional[str],
) -> list:
    """Devuelve timesheets del equipo con filtros opcionales."""
    q = db.query(Timesheet).options(joinedload(Timesheet.user))
    if week_start:
        q = q.filter(Timesheet.week_start == week_start)
    if user_id:
        q = q.filter(Timesheet.user_id == user_id)
    if status:
        q = q.filter(Timesheet.status == status)
    timesheets = q.order_by(Timesheet.week_start.desc()).all()
    return _enrich(timesheets)


def _enrich(timesheets) -> list:
    """Añade user_name y reviewer_name a los resultados."""
    result = []
    for ts in timesheets:
        item = {
            "id": ts.id,
            "user_id": ts.user_id,
            "week_start": ts.week_start,
            "week_end": ts.week_end,
            "status": ts.status.value if hasattr(ts.status, "value") else ts.status,
            "total_hours": ts.total_hours or 0,
            "billable_hours": ts.billable_hours or 0,
            "total_cost": ts.total_cost or 0,
            "submitted_at": ts.submitted_at,
            "reviewed_at": ts.reviewed_at,
            "review_notes": ts.review_notes,
            "user_name": ts.user.full_name if ts.user else None,
            "reviewer_name": None,
        }
        result.append(item)
    return result


# ── Date utilities ────────────────────────────────────────────────────────────

def get_week_bounds(week_start) -> tuple:
    """Return (week_start, week_end) for the given date, defaulting to current week."""
    if not week_start:
        today = timeutil.today()
        week_start = today - timedelta(days=today.weekday())
    return week_start, week_start + timedelta(days=6)
