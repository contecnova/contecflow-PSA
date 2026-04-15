from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session, joinedload
from typing import Optional, List
from datetime import date

from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager
from app.models.user import User, UserRole
from app.models.imputation import Imputation
from app.schemas.schemas import ImputationCreate, ImputationUpdate, ImputationOut, WeekSummary
from app.schemas.time_tracking import TimerSessionOut, TimerStartPayload, TimerStopPayload, ImputationAlertOut, LockoutStatusOut
from app.services.psa_flows import approve_imputation_flow
from app.services.imputation_service import (
    validate_and_create_imputation,
    validate_imputation_edit_allowed,
    update_imputation_fields,
    start_timer_session,
    pause_timer_session,
    resume_timer_session,
    stop_timer_session,
    timer_out,
    get_current_timer_record,
    get_week_summary,
    lockout_status_payload,
    list_alerts_payload,
    dismiss_alert_record,
)

router = APIRouter()


@router.get("", response_model=List[ImputationOut], summary="Listar imputaciones con filtros")
def list_imputations(
    user_id: Optional[str] = None,
    project_id: Optional[str] = None,
    task_id: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    response: Response = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Imputation).options(
        joinedload(Imputation.user),
        joinedload(Imputation.task),
        joinedload(Imputation.project),
    )

    # Employees and subcontractors can only see their own
    if current_user.role in (UserRole.employee, UserRole.subcontractor):
        q = q.filter(Imputation.user_id == current_user.id)
    elif user_id:
        q = q.filter(Imputation.user_id == user_id)

    if project_id:
        q = q.filter(Imputation.project_id == project_id)
    if task_id:
        q = q.filter(Imputation.task_id == task_id)
    if date_from:
        q = q.filter(Imputation.date >= date_from)
    if date_to:
        q = q.filter(Imputation.date <= date_to)

    total = q.count()
    items = q.order_by(Imputation.date.desc()).offset((page - 1) * page_size).limit(page_size).all()
    if response is not None:
        response.headers["X-Total-Count"] = str(total)
        response.headers["X-Page"] = str(page)
        response.headers["X-Page-Size"] = str(page_size)
    return items


@router.get("/my/week", response_model=WeekSummary, summary="Resumen semanal del usuario actual")
def get_my_week(
    week_start: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_week_summary(week_start, current_user, db)


@router.post("", response_model=ImputationOut, summary="Registrar horas (imputar)")
def create_imputation(
    payload: ImputationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return validate_and_create_imputation(payload, current_user, db)


@router.patch("/{imputation_id}", response_model=ImputationOut, summary="Editar imputación")
def update_imputation(
    imputation_id: str,
    payload: ImputationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    imp = db.query(Imputation).filter(Imputation.id == imputation_id).first()
    if not imp:
        raise HTTPException(status_code=404, detail="Imputación no encontrada")

    validate_imputation_edit_allowed(imp, current_user, db)
    return update_imputation_fields(imp, payload, db)


@router.delete("/{imputation_id}", summary="Eliminar imputación")
def delete_imputation(
    imputation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    imp = db.query(Imputation).filter(Imputation.id == imputation_id).first()
    if not imp:
        raise HTTPException(status_code=404, detail="Imputación no encontrada")

    validate_imputation_edit_allowed(imp, current_user, db)

    db.delete(imp)
    db.commit()
    return {"message": "Imputación eliminada"}


@router.post("/{imputation_id}/approve", summary="Aprobar imputación (manager)")
def approve_imputation(
    imputation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    approve_imputation_flow(db, imputation_id, current_user)
    return {"message": "Imputación aprobada"}


# ── Timer Endpoints ────────────────────────────────────────────────────────

@router.post("/timer/start", response_model=TimerSessionOut, summary="Start work timer")
def start_timer(
    payload: TimerStartPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Start timer for current user on a task."""
    timer = start_timer_session(payload, current_user, db)
    return timer_out(timer)


@router.post("/timer/pause", response_model=TimerSessionOut, summary="Pause timer")
def pause_timer(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    timer = pause_timer_session(current_user, db)
    return timer_out(timer)


@router.post("/timer/resume", response_model=TimerSessionOut, summary="Resume timer")
def resume_timer(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    timer = resume_timer_session(current_user, db)
    return timer_out(timer)


@router.post("/timer/stop", response_model=ImputationOut, summary="Stop timer and create imputation")
def stop_timer(
    payload: TimerStopPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return stop_timer_session(payload, current_user, db)


@router.get("/timer/current", response_model=Optional[TimerSessionOut], summary="Get active timer")
def get_current_timer(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    timer = get_current_timer_record(db, current_user)
    if not timer:
        return None
    return timer_out(timer)


# ── Lockout Status Endpoints ───────────────────────────────────────────────

@router.get("/lockout-status", response_model=LockoutStatusOut, summary="Get imputation lockout status")
def get_lockout_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return lockout_status_payload(current_user, db)


# ── Imputation Alerts ──────────────────────────────────────────────────────

@router.get("/alerts", response_model=List[ImputationAlertOut], summary="Get missing imputation alerts")
def get_imputation_alerts(
    acknowledged: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get alerts for missing/incomplete imputations."""
    return list_alerts_payload(db, current_user, acknowledged)


@router.post("/alerts/{alert_id}/dismiss", summary="Dismiss imputation alert")
def dismiss_alert(
    alert_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Dismiss/snooze an imputation alert."""
    return dismiss_alert_record(db, alert_id, current_user)
