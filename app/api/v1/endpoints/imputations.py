from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, and_
from sqlalchemy.exc import IntegrityError
from typing import Optional, List
from datetime import date, datetime, timedelta, timezone

from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager
from app.models.user import User, UserRole
from app.models.imputation import Imputation, TimerSession, ImputationAlert
from app.models.task import Task, TaskStatus
from app.models.project import Project, ProjectMember
from app.models.financial import Timesheet, TimesheetStatus
from app.models.mfa import Organization
from app.schemas.imputations import ImputationCreate, ImputationUpdate, ImputationOut, WeekSummary
from app.schemas.time_tracking import TimerSessionOut, TimerStartPayload, TimerStopPayload, ImputationAlertOut, LockoutStatusOut
from app.core.config import settings
from app.services.psa_flows import approve_imputation_flow

router = APIRouter()


def _compute_cost(user: User, hours: float) -> float:
    base_rate = user.hourly_rate or 0.0
    return round(base_rate * hours, 2)


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
    if not week_start:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    imputations = db.query(Imputation).options(
        joinedload(Imputation.project)
    ).filter(
        Imputation.user_id == current_user.id,
        Imputation.date >= week_start,
        Imputation.date <= week_end,
    ).all()

    total_hours = sum(i.hours for i in imputations)
    capacity = current_user.weekly_capacity_hours or settings.DEFAULT_WEEKLY_CAPACITY_HOURS
    load_pct = round((total_hours / capacity) * 100, 1)

    # By project
    by_project = {}
    for imp in imputations:
        pid = imp.project_id
        if pid not in by_project:
            by_project[pid] = {"project_id": pid, "project_name": imp.project.name if imp.project else "?", "hours": 0}
        by_project[pid]["hours"] += imp.hours

    # By day
    by_day = {}
    for imp in imputations:
        d = str(imp.date)
        if d not in by_day:
            by_day[d] = {"date": d, "hours": 0}
        by_day[d]["hours"] += imp.hours

    return WeekSummary(
        user_id=current_user.id,
        week_start=week_start,
        week_end=week_end,
        total_hours=total_hours,
        capacity_hours=capacity,
        load_pct=load_pct,
        by_project=list(by_project.values()),
        by_day=sorted(by_day.values(), key=lambda x: x["date"]),
    )


@router.post("", response_model=ImputationOut, summary="Registrar horas (imputar)")
def create_imputation(
    payload: ImputationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # P0-3: Enforce imputation lockout — non-admins cannot log hours in the locked period
    if current_user.role != UserRole.admin:
        _org = db.query(Organization).first()
        lockout_days = (
            _org.imputation_lockout_days
            if _org and _org.imputation_lockout_days is not None
            else settings.DEFAULT_IMPUTATION_LOCKOUT_DAYS
        )
        earliest_allowed = date.today() - timedelta(days=lockout_days)
        if payload.date < earliest_allowed:
            raise HTTPException(
                status_code=400,
                detail=f"No puedes imputar en fechas anteriores a hace {lockout_days} días ({earliest_allowed}). Contacta con tu manager si necesitas una corrección.",
            )
        today_utc = datetime.now(timezone.utc).date()
        if payload.date > today_utc:
            raise HTTPException(status_code=400, detail="No puedes imputar en fechas futuras.")

    # Validate project exists
    project = db.query(Project).filter(Project.id == payload.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")

    task = None
    # Validate task early (needed for assignment rules and duplicate checks).
    if payload.task_id:
        task = db.query(Task).filter(
            Task.id == payload.task_id,
            Task.project_id == payload.project_id,
        ).first()
        if not task:
            raise HTTPException(status_code=404, detail="Tarea no encontrada o no pertenece al proyecto")

    # Validate user assignment to project for non-admin users.
    # Strict mode: user must be explicit project member, project PM, or task assignee.
    if current_user.role != UserRole.admin:
        is_member = db.query(ProjectMember.id).filter(
            ProjectMember.project_id == payload.project_id,
            ProjectMember.user_id == current_user.id,
        ).first()
        is_pm = project.pm_id == current_user.id
        is_task_assignee = bool(task and task.assignee_id == current_user.id)
        if not (is_member or is_pm or is_task_assignee):
            raise HTTPException(
                status_code=403,
                detail="No puedes imputar horas en un proyecto al que no estás asignado.",
            )

    # Block imputations to closed or cancelled projects
    from app.models.project import ProjectStatus as _PS
    if project.status in (_PS.completed, _PS.closed, _PS.cancelled, _PS.archived):
        raise HTTPException(
            status_code=400,
            detail=f"No puedes imputar horas a un proyecto en estado '{project.status}'. Contacta con el PM si necesitas registrar horas históricas.",
        )

    # Validate task status and duplicates if task provided
    if task:

        if task.status in (TaskStatus.done, TaskStatus.cancelled):
            raise HTTPException(
                status_code=400,
                detail=f"No puedes imputar horas en una tarea con estado '{task.status}'.",
            )

        # Duplicate guard: same user + same task + same date is not allowed.
        duplicate = db.query(Imputation.id).filter(
            Imputation.user_id == current_user.id,
            Imputation.task_id == payload.task_id,
            Imputation.date == payload.date,
        ).first()
        if duplicate:
            raise HTTPException(
                status_code=409,
                detail="Ya existe una imputación para esta tarea en esa fecha.",
            )

    # Validate that user has hourly rate assigned
    # Subcontractors may not have a rate configured yet (cost tracked via contract); skip check for them
    if (not current_user.hourly_rate or current_user.hourly_rate <= 0) and current_user.role != UserRole.subcontractor:
        raise HTTPException(
            status_code=400,
            detail="No puedes imputar horas sin tener una tarifa horaria asignada. Contacta con Recursos Humanos."
        )

    # Check daily capacity (warn if >24h but allow)
    existing_hours = db.query(func.sum(Imputation.hours)).filter(
        Imputation.user_id == current_user.id,
        Imputation.date == payload.date,
    ).scalar() or 0.0

    if existing_hours + payload.hours > 24:
        raise HTTPException(
            status_code=400,
            detail=f"No puedes imputar más de 24h en un día. Ya tienes {existing_hours}h registradas."
        )

    # Check weekly capacity (max 40h per week for standard employees)
    week_start = payload.date - timedelta(days=payload.date.weekday())  # Monday
    week_end = week_start + timedelta(days=6)  # Sunday

    weekly_hours = db.query(func.sum(Imputation.hours)).filter(
        and_(
            Imputation.user_id == current_user.id,
            Imputation.date >= week_start,
            Imputation.date <= week_end,
        )
    ).scalar() or 0.0

    weekly_capacity = current_user.weekly_capacity_hours or 40.0
    if weekly_hours + payload.hours > weekly_capacity:
        raise HTTPException(
            status_code=400,
            detail=f"Excederías la capacidad semanal ({weekly_capacity}h). Semana actual: {weekly_hours}h, nueva imputación: {payload.hours}h."
        )
    rate = current_user.hourly_rate
    cost = _compute_cost(current_user, payload.hours)

    imputation = Imputation(
        user_id=current_user.id,
        task_id=payload.task_id,
        project_id=payload.project_id,
        date=payload.date,
        hours=payload.hours,
        description=payload.description,
        is_billable=payload.is_billable,
        hourly_rate_snapshot=rate,
        cost_amount=cost,
    )
    db.add(imputation)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Ya existe una imputación para esta tarea en esa fecha.",
        ) from exc
    db.refresh(imputation)
    return imputation


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

    # Only owner or admin can edit
    if imp.user_id != current_user.id and current_user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="No puedes editar imputaciones de otros")

    if imp.is_approved and current_user.role != UserRole.admin:
        raise HTTPException(status_code=400, detail="No se puede editar una imputación ya aprobada")

    # P0-3: Imputation lockout enforcement on edit
    if current_user.role != UserRole.admin:
        _org = db.query(Organization).first()
        lockout_days = (
            _org.imputation_lockout_days
            if _org and _org.imputation_lockout_days is not None
            else settings.DEFAULT_IMPUTATION_LOCKOUT_DAYS
        )
        earliest_allowed = date.today() - timedelta(days=lockout_days)
        if imp.date < earliest_allowed:
            raise HTTPException(
                status_code=400,
                detail=f"No puedes editar imputaciones de hace más de {lockout_days} días.",
            )

    # Prevent edit if timesheet is submitted/approved and user is not admin
    week_start = imp.date - timedelta(days=imp.date.weekday())
    ts = db.query(Timesheet).filter(
        Timesheet.user_id == imp.user_id,
        Timesheet.week_start == week_start,
    ).first()
    if ts and ts.status in [TimesheetStatus.submitted, TimesheetStatus.approved] and current_user.role != UserRole.admin:
        raise HTTPException(status_code=400, detail="No se puede editar imputaciones en una hoja de tiempo ya enviada o aprobada")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(imp, field, value)

    # Recalculate cost if hours changed, preserving historical rate snapshot
    if payload.hours is not None:
        rate = imp.hourly_rate_snapshot
        if rate is not None and rate > 0:
            imp.cost_amount = round(rate * payload.hours, 2)
        # If rate snapshot is missing, preserve existing cost_amount to avoid data corruption

    db.commit()
    db.refresh(imp)
    return imp


@router.delete("/{imputation_id}", summary="Eliminar imputación")
def delete_imputation(
    imputation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    imp = db.query(Imputation).filter(Imputation.id == imputation_id).first()
    if not imp:
        raise HTTPException(status_code=404, detail="Imputación no encontrada")

    if imp.user_id != current_user.id and current_user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="No puedes eliminar imputaciones de otros")

    if imp.is_approved and current_user.role != UserRole.admin:
        raise HTTPException(status_code=400, detail="No se puede eliminar una imputación ya aprobada")

    # Prevent delete if timesheet is submitted/approved and user is not admin
    week_start = imp.date - timedelta(days=imp.date.weekday())
    ts = db.query(Timesheet).filter(
        Timesheet.user_id == imp.user_id,
        Timesheet.week_start == week_start,
    ).first()
    if ts and ts.status in [TimesheetStatus.submitted, TimesheetStatus.approved] and current_user.role != UserRole.admin:
        raise HTTPException(status_code=400, detail="No se puede eliminar imputaciones en una hoja de tiempo ya enviada o aprobada")

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
    # Check if user already has active timer
    existing = db.query(TimerSession).filter(
        and_(
            TimerSession.user_id == current_user.id,
            TimerSession.ended_at == None,
        )
    ).first()

    if existing:
        raise HTTPException(status_code=409, detail="User already has an active timer")

    # ── Same pre-conditions as create_imputation ─────────────────────────
    # 1. Hourly rate required
    if not current_user.hourly_rate or current_user.hourly_rate <= 0:
        raise HTTPException(
            status_code=400,
            detail="No puedes iniciar el cronómetro sin tener una tarifa horaria asignada. Contacta con Recursos Humanos.",
        )

    # 2. Project must exist
    project = db.query(Project).filter(Project.id == payload.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")

    # 3. Task must belong to project and (for non-admins) be assigned to current user
    if payload.task_id:
        task = db.query(Task).filter(
            Task.id == payload.task_id,
            Task.project_id == payload.project_id,
        ).first()
        if not task:
            raise HTTPException(status_code=404, detail="Tarea no encontrada o no pertenece al proyecto")
        if current_user.role != UserRole.admin and task.assignee_id != current_user.id:
            raise HTTPException(
                status_code=403,
                detail="No puedes iniciar el cronómetro en una tarea que no está asignada a ti.",
            )
    # ─────────────────────────────────────────────────────────────────────

    now = datetime.now(timezone.utc)
    timer = TimerSession(
        user_id=current_user.id,
        task_id=payload.task_id,
        project_id=payload.project_id,
        started_at=now,
    )
    db.add(timer)
    db.flush()
    db.commit()
    db.refresh(timer)

    return _timer_out(timer)


@router.post("/timer/pause", response_model=TimerSessionOut, summary="Pause timer")
def pause_timer(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Pause active timer."""
    timer = db.query(TimerSession).filter(
        and_(
            TimerSession.user_id == current_user.id,
            TimerSession.ended_at == None,
        )
    ).first()

    if not timer:
        raise HTTPException(status_code=404, detail="No active timer found")

    timer.paused_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(timer)
    return _timer_out(timer)


@router.post("/timer/resume", response_model=TimerSessionOut, summary="Resume timer")
def resume_timer(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Resume paused timer."""
    timer = db.query(TimerSession).filter(
        and_(
            TimerSession.user_id == current_user.id,
            TimerSession.ended_at == None,
            TimerSession.paused_at != None,
        )
    ).first()

    if not timer:
        raise HTTPException(status_code=404, detail="No paused timer found")

    # Add pause duration
    if timer.paused_at:
        paused_at = timer.paused_at if timer.paused_at.tzinfo else timer.paused_at.replace(tzinfo=timezone.utc)
        pause_duration = (datetime.now(timezone.utc) - paused_at).total_seconds()
        timer.paused_duration_secs += int(pause_duration)

    timer.paused_at = None
    db.commit()
    db.refresh(timer)
    return _timer_out(timer)


@router.post("/timer/stop", response_model=ImputationOut, summary="Stop timer and create imputation")
def stop_timer(
    payload: TimerStopPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Stop timer and create imputation from elapsed time."""
    timer = db.query(TimerSession).filter(
        and_(
            TimerSession.user_id == current_user.id,
            TimerSession.ended_at == None,
        )
    ).first()

    if not timer:
        raise HTTPException(status_code=404, detail="No active timer found")

    # Hourly rate required to register the imputation (consistent with create_imputation)
    if not current_user.hourly_rate or current_user.hourly_rate <= 0:
        raise HTTPException(
            status_code=400,
            detail="No puedes registrar horas sin tener una tarifa horaria asignada. Contacta con Recursos Humanos.",
        )

    # Calculate elapsed time
    now = datetime.now(timezone.utc)
    started = timer.started_at if timer.started_at.tzinfo else timer.started_at.replace(tzinfo=timezone.utc)
    elapsed = (now - started).total_seconds()
    pause_duration = timer.paused_duration_secs or 0
    # If timer is currently paused, also exclude the ongoing pause from active time
    if timer.paused_at:
        paused_at = timer.paused_at if timer.paused_at.tzinfo else timer.paused_at.replace(tzinfo=timezone.utc)
        pause_duration += (now - paused_at).total_seconds()
    active_seconds = max(0, elapsed - pause_duration)  # Prevent negative time
    hours = max(0.25, round(active_seconds / 3600, 2))  # Minimum 15 minutes

    # Create imputation
    imputation = Imputation(
        user_id=current_user.id,
        task_id=timer.task_id,
        project_id=timer.project_id,
        date=date.today(),
        hours=hours,
        description=payload.description,
        is_billable=payload.is_billable,
        hourly_rate_snapshot=current_user.hourly_rate,
        cost_amount=round((current_user.hourly_rate or 0) * hours, 2),
        timer_session_id=timer.id,
    )
    db.add(imputation)
    db.flush()

    # Link timer to imputation and close
    timer.imputation_id = imputation.id
    timer.ended_at = datetime.now(timezone.utc)
    db.commit()
    # Reload with relationships so ImputationOut serializes correctly
    db.refresh(imputation)
    imputation = db.query(Imputation).options(
        joinedload(Imputation.user),
        joinedload(Imputation.task),
        joinedload(Imputation.project),
    ).filter(Imputation.id == imputation.id).first()
    return imputation


@router.get("/timer/current", response_model=Optional[TimerSessionOut], summary="Get active timer")
def get_current_timer(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get currently active timer for user."""
    timer = db.query(TimerSession).filter(
        and_(
            TimerSession.user_id == current_user.id,
            TimerSession.ended_at == None,
        )
    ).first()

    if not timer:
        return None

    return _timer_out(timer)


def _timer_out(timer: TimerSession) -> TimerSessionOut:
    """Serialize a TimerSession to TimerSessionOut with computed elapsed seconds."""
    now = datetime.now(timezone.utc)
    started = timer.started_at
    # Ensure timezone-aware for arithmetic
    if started.tzinfo is None:
        from datetime import timezone as _tz
        started = started.replace(tzinfo=_tz.utc)
    paused_duration = timer.paused_duration_secs or 0
    if timer.paused_at:
        paused_at = timer.paused_at if timer.paused_at.tzinfo else timer.paused_at.replace(tzinfo=timezone.utc)
        total_elapsed = max(0, int((paused_at - started).total_seconds()) - paused_duration)
    else:
        total_elapsed = max(0, int((now - started).total_seconds()) - paused_duration)
    return TimerSessionOut(
        id=timer.id,
        user_id=timer.user_id,
        task_id=timer.task_id,
        project_id=timer.project_id,
        started_at=started.isoformat() if started.tzinfo else started.replace(tzinfo=timezone.utc).isoformat(),
        paused_at=timer.paused_at,
        paused_duration_secs=paused_duration,
        ended_at=timer.ended_at,
        total_elapsed_seconds=total_elapsed,
    )


# ── Lockout Status Endpoints ───────────────────────────────────────────────

@router.get("/lockout-status", response_model=LockoutStatusOut, summary="Get imputation lockout status")
def get_lockout_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get lockout status for editing imputations (configurable per organization)."""
    # Get lockout days from organization
    org = db.query(Organization).filter(
        Organization.id == current_user.organization_id
    ).first() if current_user.organization_id else None

    lockout_days = org.imputation_lockout_days if org else settings.DEFAULT_IMPUTATION_LOCKOUT_DAYS

    today = date.today()
    lockout_cutoff = today - timedelta(days=lockout_days)

    return LockoutStatusOut(
        lockout_days=lockout_days,
        current_date=today,
        lockout_cutoff_date=lockout_cutoff,
        locked_date_ranges=[],  # Simplified
        editable_date_ranges=[],  # Simplified
    )


# ── Imputation Alerts ──────────────────────────────────────────────────────

@router.get("/alerts", response_model=List[ImputationAlertOut], summary="Get missing imputation alerts")
def get_imputation_alerts(
    acknowledged: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get alerts for missing/incomplete imputations."""
    q = db.query(ImputationAlert).filter(ImputationAlert.user_id == current_user.id)

    if not acknowledged:
        q = q.filter(ImputationAlert.dismissed_at == None)

    alerts = q.order_by(ImputationAlert.alert_date.desc()).all()

    return [
        ImputationAlertOut(
            id=a.id,
            user_id=a.user_id,
            alert_date=a.alert_date,
            alert_type=a.alert_type,
            created_at=a.created_at,
            dismissed_at=a.dismissed_at,
        )
        for a in alerts
    ]


@router.post("/alerts/{alert_id}/dismiss", summary="Dismiss imputation alert")
def dismiss_alert(
    alert_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Dismiss/snooze an imputation alert."""
    alert = db.query(ImputationAlert).filter(ImputationAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    if alert.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Cannot dismiss another user's alert")

    alert.dismissed_at = datetime.now(timezone.utc)
    db.commit()

    return {"status": "dismissed"}
