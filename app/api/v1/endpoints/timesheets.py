from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from datetime import date, datetime, timedelta, timezone

from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager
from app.core.abac_enforce import enforce_abac
from app.models.user import User
from app.models.imputation import Imputation
from app.models.financial import Timesheet, TimesheetStatus
from app.services.psa_flows import (
    review_timesheet_flow,
    send_back_timesheet_flow,
    submit_timesheet_flow,
    sync_timesheet_from_imputations_flow,
)
import app.services.timesheet_service as _tsvc
from app.schemas.timesheets import (
    TimesheetOut,
    TimesheetReview,
    ImputationLine,
    TimesheetSendBackPayload as SendBackPayload,
)

router = APIRouter()


_get_week_bounds = _tsvc.get_week_bounds
_sync_timesheet = sync_timesheet_from_imputations_flow


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/my", response_model=List[TimesheetOut], summary="Mis timesheets")
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
            "user_id": ts.user_id,
            "week_start": ts.week_start,
            "week_end": ts.week_end,
            "status": ts.status,
            "total_hours": ts.total_hours,
            "billable_hours": ts.billable_hours,
            "total_cost": ts.total_cost,
            "submitted_at": ts.submitted_at,
            "reviewed_at": ts.reviewed_at,
            "review_notes": ts.review_notes,
        })
    return results


@router.get("/my/{week_start}/lines", summary="Líneas de un timesheet")
def get_timesheet_lines(
    week_start: date,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _tsvc.get_timesheet_lines(db, current_user.id, week_start)


@router.post("/my/{week_start}/submit", summary="Enviar timesheet para aprobación")
def submit_timesheet(
    week_start: date,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ts = submit_timesheet_flow(db, current_user.id, week_start)
    return {"message": "Timesheet enviado para aprobación", "status": ts.status}


@router.get("/pending", response_model=List[TimesheetOut], summary="Timesheets pendientes de revisión (managers)")
def get_pending_timesheets(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return _tsvc.list_pending_timesheets(db)


@router.get("/team", response_model=List[TimesheetOut], summary="Todos los timesheets del equipo")
def get_team_timesheets(
    week_start: Optional[date] = None,
    user_id: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    enforce_abac(db, current_user, "timesheet", action="read")
    return _tsvc.list_team_timesheets(db, week_start, user_id, status)


@router.post("/{timesheet_id}/review", summary="Aprobar o rechazar timesheet")
def review_timesheet(
    timesheet_id: str,
    payload: TimesheetReview,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    enforce_abac(db, current_user, "timesheet", timesheet_id, action="approve")
    ts = review_timesheet_flow(db, timesheet_id, current_user, payload.approved, payload.notes)
    action = "aprobado" if payload.approved else "rechazado"
    return {"message": f"Timesheet {action}", "status": ts.status}




@router.post("/{timesheet_id}/send-back", summary="Devolver timesheet al empleado para corrección")
def send_back_timesheet(
    timesheet_id: str,
    payload: SendBackPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """Return a submitted timesheet to the employee so they can correct and re-submit it."""
    ts = send_back_timesheet_flow(db, timesheet_id, current_user, payload.notes)
    return {"message": "Timesheet devuelto para corrección", "status": ts.status}
