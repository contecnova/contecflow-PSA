from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from typing import Optional
from datetime import date, datetime, timedelta, timezone
from pydantic import BaseModel

from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager
from app.core.abac_enforce import enforce_abac
from app.models.user import User
from app.models.imputation import Imputation
from app.models.financial import Timesheet, TimesheetStatus

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class TimesheetOut(BaseModel):
    id: str
    user_id: str
    week_start: date
    week_end: date
    status: str
    total_hours: float
    billable_hours: float
    total_cost: float
    submitted_at: Optional[date] = None
    reviewed_at: Optional[date] = None
    review_notes: Optional[str] = None
    user_name: Optional[str] = None
    reviewer_name: Optional[str] = None
    model_config = {"from_attributes": True}

class TimesheetReview(BaseModel):
    approved: bool
    notes: Optional[str] = None

class ImputationLine(BaseModel):
    id: str
    date: date
    hours: float
    billable_hours: float
    cost: float
    project_name: str
    project_code: str
    description: Optional[str] = None
    is_billable: bool
    is_approved: bool


def _get_week_bounds(week_start: Optional[date]) -> tuple:
    if not week_start:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
    return week_start, week_start + timedelta(days=6)


def _sync_timesheet(db: Session, user_id: str, week_start: date) -> Timesheet:
    """Create or update timesheet from imputations."""
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
    else:
        if ts.status in [TimesheetStatus.draft, TimesheetStatus.rejected]:
            ts.total_hours = total
            ts.billable_hours = billable
            ts.total_cost = cost

    db.commit()
    db.refresh(ts)
    return ts


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/my", summary="Mis timesheets")
def get_my_timesheets(
    weeks: int = Query(8, ge=1, le=52),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    today = date.today()
    results = []
    for w in range(weeks):
        ws = today - timedelta(days=today.weekday()) - timedelta(weeks=w)
        ts = _sync_timesheet(db, current_user.id, ws)
        results.append({
            "id": ts.id,
            "week_start": str(ts.week_start),
            "week_end": str(ts.week_end),
            "status": ts.status,
            "total_hours": ts.total_hours,
            "billable_hours": ts.billable_hours,
            "total_cost": ts.total_cost,
            "submitted_at": str(ts.submitted_at) if ts.submitted_at else None,
            "reviewed_at": str(ts.reviewed_at) if ts.reviewed_at else None,
            "review_notes": ts.review_notes,
        })
    return results


@router.get("/my/{week_start}/lines", summary="Líneas de un timesheet")
def get_timesheet_lines(
    week_start: date,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    week_end = week_start + timedelta(days=6)
    imps = db.query(Imputation).options(
        joinedload(Imputation.project)
    ).filter(
        Imputation.user_id == current_user.id,
        Imputation.date >= week_start,
        Imputation.date <= week_end,
    ).order_by(Imputation.date).all()

    return [{
        "id": i.id,
        "date": str(i.date),
        "hours": i.hours,
        "project_name": i.project.name if i.project else "—",
        "project_code": i.project.code if i.project else "—",
        "description": i.description,
        "is_billable": i.is_billable,
        "is_approved": i.is_approved,
        "cost": i.cost_amount or 0,
    } for i in imps]


@router.post("/my/{week_start}/submit", summary="Enviar timesheet para aprobación")
def submit_timesheet(
    week_start: date,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ts = _sync_timesheet(db, current_user.id, week_start)
    if ts.status not in [TimesheetStatus.draft, TimesheetStatus.rejected]:
        raise HTTPException(400, "Solo se pueden enviar timesheets en borrador o rechazados")
    if ts.total_hours == 0:
        raise HTTPException(400, "No puedes enviar un timesheet vacío")
    ts.status = TimesheetStatus.submitted
    ts.submitted_at = datetime.now(timezone.utc)
    db.commit()
    return {"message": "Timesheet enviado para aprobación", "status": ts.status}


@router.get("/pending", summary="Timesheets pendientes de revisión (managers)")
def get_pending_timesheets(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    ts_list = db.query(Timesheet).options(
        joinedload(Timesheet.user)
    ).filter(
        Timesheet.status == TimesheetStatus.submitted
    ).order_by(Timesheet.week_start.desc()).all()

    return [{
        "id": ts.id,
        "week_start": str(ts.week_start),
        "week_end": str(ts.week_end),
        "status": ts.status,
        "total_hours": ts.total_hours,
        "billable_hours": ts.billable_hours,
        "total_cost": ts.total_cost,
        "user_id": ts.user_id,
        "user_name": ts.user.full_name if ts.user else "—",
        "submitted_at": str(ts.submitted_at) if ts.submitted_at else None,
    } for ts in ts_list]


@router.get("/team", summary="Todos los timesheets del equipo")
def get_team_timesheets(
    week_start: Optional[date] = None,
    user_id: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    enforce_abac(db, current_user, "timesheet", action="read")
    q = db.query(Timesheet).options(joinedload(Timesheet.user))
    if week_start:
        q = q.filter(Timesheet.week_start == week_start)
    if user_id:
        q = q.filter(Timesheet.user_id == user_id)
    if status:
        q = q.filter(Timesheet.status == status)
    ts_list = q.order_by(Timesheet.week_start.desc()).limit(200).all()

    return [{
        "id": ts.id,
        "week_start": str(ts.week_start),
        "week_end": str(ts.week_end),
        "status": ts.status,
        "total_hours": ts.total_hours,
        "billable_hours": ts.billable_hours,
        "total_cost": ts.total_cost,
        "user_id": ts.user_id,
        "user_name": ts.user.full_name if ts.user else "—",
        "submitted_at": str(ts.submitted_at) if ts.submitted_at else None,
        "reviewed_at": str(ts.reviewed_at) if ts.reviewed_at else None,
        "review_notes": ts.review_notes,
    } for ts in ts_list]


@router.post("/{timesheet_id}/review", summary="Aprobar o rechazar timesheet")
def review_timesheet(
    timesheet_id: str,
    payload: TimesheetReview,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    enforce_abac(db, current_user, "timesheet", timesheet_id, action="approve")
    ts = db.query(Timesheet).filter(Timesheet.id == timesheet_id).first()
    if not ts:
        raise HTTPException(404, "Timesheet no encontrado")
    if ts.status != TimesheetStatus.submitted:
        raise HTTPException(400, "Solo se pueden revisar timesheets enviados")

    ts.status = TimesheetStatus.approved if payload.approved else TimesheetStatus.rejected
    ts.reviewed_by = current_user.id
    ts.reviewed_at = datetime.now(timezone.utc)
    ts.review_notes = payload.notes

    # If approved, mark all imputations as approved
    if payload.approved:
        week_end = ts.week_start + timedelta(days=6)
        db.query(Imputation).filter(
            Imputation.user_id == ts.user_id,
            Imputation.date >= ts.week_start,
            Imputation.date <= week_end,
        ).update({"is_approved": True, "approved_by": current_user.id, "approved_at": datetime.now(timezone.utc)})

    db.commit()
    action = "aprobado" if payload.approved else "rechazado"
    return {"message": f"Timesheet {action}", "status": ts.status}


class SendBackPayload(BaseModel):
    notes: str = ""


@router.post("/{timesheet_id}/send-back", summary="Devolver timesheet al empleado para corrección")
def send_back_timesheet(
    timesheet_id: str,
    payload: SendBackPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """Return a submitted timesheet to the employee so they can correct and re-submit it."""
    ts = db.query(Timesheet).filter(Timesheet.id == timesheet_id).first()
    if not ts:
        raise HTTPException(404, "Timesheet no encontrado")
    if ts.status != TimesheetStatus.submitted:
        raise HTTPException(400, "Solo se pueden devolver timesheets en estado 'enviado'")

    ts.status = TimesheetStatus.rejected
    ts.reviewed_by = current_user.id
    ts.reviewed_at = datetime.now(timezone.utc)
    note_prefix = "[Devuelto para corrección]"
    ts.review_notes = f"{note_prefix} {payload.notes}".strip()

    db.commit()
    return {"message": "Timesheet devuelto para corrección", "status": ts.status}
