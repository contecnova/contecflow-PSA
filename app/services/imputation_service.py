"""
imputation_service.py — Lógica de negocio para imputaciones y cronómetros.

Funciones exportadas:
  compute_cost(user, hours)
  validate_and_create_imputation(payload, current_user, db)
  validate_imputation_edit_allowed(imp, current_user, db)
  start_timer_session(payload, current_user, db)
  pause_timer_session(current_user, db)
  resume_timer_session(current_user, db)
  stop_timer_session(payload, current_user, db)
  compute_timer_elapsed(timer) -> int (seconds)
  get_week_summary(week_start, current_user, db)
  get_lockout_cutoff(current_user, db)
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.models.user import User, UserRole
from app.models.financial import Timesheet, TimesheetStatus
from app.models.imputation import Imputation
from app.models.imputation import TimerSession
from app.models.imputation import ImputationAlert
from app.models.mfa import Organization
from app.models.project import ProjectMember
from app.models.project import Project, ProjectStatus as _PS
from app.models.task import Task, TaskStatus
from app.models.user import User as UserModel
from app.schemas import WeekSummary
from app.schemas.time_tracking import TimerSessionOut
from app.schemas.time_tracking import LockoutStatusOut
from app.schemas.time_tracking import ImputationAlertOut
from fastapi import HTTPException


# ── Cost ───────────────────────────────────────────────────────────────────────

def compute_cost(user: User, hours: float) -> float:
    base_rate = user.hourly_rate or 0.0
    return round(base_rate * hours, 2)


# ── Lockout ────────────────────────────────────────────────────────────────────

def get_lockout_cutoff(current_user: User, db: Session) -> date:
    org = None
    if current_user.organization_id:
        org = db.query(Organization).filter(
            Organization.id == current_user.organization_id
        ).first()
    lockout_days = (
        org.imputation_lockout_days
        if org and org.imputation_lockout_days is not None
        else settings.DEFAULT_IMPUTATION_LOCKOUT_DAYS
    )
    return date.today() - timedelta(days=lockout_days)


# ── Membership guard ───────────────────────────────────────────────────────────

def _assert_project_membership(project, task, current_user: User, db: Session) -> None:
    """Raises 403 if the current user is not allowed to log time on the project.

    Allowed if the user is:
      - admin (bypass)
      - the project PM
      - an explicit ProjectMember of the project
      - the assignee of the specific task (when a task is provided)
    """
    if current_user.role == UserRole.admin:
        return

    is_pm = project.pm_id == current_user.id
    is_member = db.query(ProjectMember.id).filter(
        ProjectMember.project_id == project.id,
        ProjectMember.user_id == current_user.id,
    ).first() is not None
    is_task_assignee = bool(task and task.assignee_id == current_user.id)
    if not (is_pm or is_member or is_task_assignee):
        raise HTTPException(
            status_code=403,
            detail="No puedes imputar horas en un proyecto al que no estás asignado.",
        )


# ── Validate & create ──────────────────────────────────────────────────────────

def validate_and_create_imputation(payload, current_user: User, db: Session):
    """
    Validates all business rules and creates an Imputation record.
    Returns the newly created Imputation ORM object.
    Raises HTTPException on any violation.
    """

    # Lockout enforcement
    if current_user.role != UserRole.admin:
        earliest_allowed = get_lockout_cutoff(current_user, db)
        if payload.date < earliest_allowed:
            lockout_days = (date.today() - earliest_allowed).days
            raise HTTPException(
                status_code=400,
                detail=(
                    f"No puedes imputar en fechas anteriores a hace {lockout_days} días "
                    f"({earliest_allowed}). Contacta con tu manager si necesitas una corrección."
                ),
            )
        today_utc = datetime.now(timezone.utc).date()
        if payload.date > today_utc:
            raise HTTPException(status_code=400, detail="No puedes imputar en fechas futuras.")

    project = db.query(Project).filter(Project.id == payload.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")

    task = None
    if payload.task_id:
        task = db.query(Task).filter(
            Task.id == payload.task_id,
            Task.project_id == payload.project_id,
        ).first()
        if not task:
            raise HTTPException(status_code=404, detail="Tarea no encontrada o no pertenece al proyecto")

    # Assignment validation — centralised in helper
    _assert_project_membership(project, task, current_user, db)

    # Project status check
    if project.status in (_PS.completed, _PS.closed, _PS.cancelled, _PS.archived):
        raise HTTPException(
            status_code=400,
            detail=f"No puedes imputar horas a un proyecto en estado '{project.status}'. Contacta con el PM si necesitas registrar horas históricas.",
        )

    # Hourly rate required
    if (not current_user.hourly_rate or current_user.hourly_rate <= 0) and current_user.role != UserRole.subcontractor:
        raise HTTPException(
            status_code=400,
            detail="No puedes imputar horas sin tener una tarifa horaria asignada. Contacta con Recursos Humanos.",
        )

    # Daily cap — checked before duplicate so exceeding 24h always returns 400
    existing_hours = db.query(func.sum(Imputation.hours)).filter(
        Imputation.user_id == current_user.id,
        Imputation.date == payload.date,
    ).scalar() or 0.0
    if existing_hours + payload.hours > 24:
        raise HTTPException(
            status_code=400,
            detail=f"No puedes imputar más de 24h en un día. Ya tienes {existing_hours}h registradas.",
        )

    if task:
        if task.status in (TaskStatus.done, TaskStatus.cancelled):
            raise HTTPException(
                status_code=400,
                detail=f"No puedes imputar horas en una tarea con estado '{task.status}'.",
            )
        duplicate = db.query(Imputation.id).filter(
            Imputation.user_id == current_user.id,
            Imputation.task_id == payload.task_id,
            Imputation.date == payload.date,
        ).first()
        if duplicate:
            raise HTTPException(status_code=409, detail="Ya existe una imputación para esta tarea en esa fecha.")
    else:
        # task_id is None: NULL != NULL in SQL so the unique index doesn't protect us;
        # enforce the duplicate check explicitly at the application level.
        dup = db.query(Imputation.id).filter(
            Imputation.user_id == current_user.id,
            Imputation.project_id == payload.project_id,
            Imputation.task_id.is_(None),
            Imputation.date == payload.date,
        ).first()
        if dup:
            raise HTTPException(
                status_code=409,
                detail="Ya existe una imputación sin tarea para este proyecto en esa fecha.",
            )

    # Weekly cap
    week_start = payload.date - timedelta(days=payload.date.weekday())
    week_end = week_start + timedelta(days=6)
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
            detail=f"Excederías la capacidad semanal ({weekly_capacity}h). Semana actual: {weekly_hours}h, nueva imputación: {payload.hours}h.",
        )

    rate = current_user.hourly_rate
    cost = compute_cost(current_user, payload.hours)

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
        raise HTTPException(status_code=409, detail="Ya existe una imputación para esta tarea en esa fecha.") from exc
    db.refresh(imputation)
    return imputation


def validate_imputation_edit_allowed(imp, current_user: User, db: Session) -> None:
    """
    Validates that an existing imputation can be edited/deleted.
    Raises HTTPException on any violation.
    """

    if imp.user_id != current_user.id and current_user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="No puedes editar imputaciones de otros")

    if imp.is_approved and current_user.role != UserRole.admin:
        raise HTTPException(status_code=400, detail="No se puede editar una imputación ya aprobada")

    if current_user.role != UserRole.admin:
        earliest_allowed = get_lockout_cutoff(current_user, db)
        if imp.date < earliest_allowed:
            lockout_days = (date.today() - earliest_allowed).days
            raise HTTPException(
                status_code=400,
                detail=f"No puedes editar imputaciones de hace más de {lockout_days} días.",
            )

    week_start = imp.date - timedelta(days=imp.date.weekday())
    ts = db.query(Timesheet).filter(
        Timesheet.user_id == imp.user_id,
        Timesheet.week_start == week_start,
    ).first()
    if ts and ts.status in [TimesheetStatus.submitted, TimesheetStatus.approved] and current_user.role != UserRole.admin:
        raise HTTPException(
            status_code=400,
            detail="No se puede editar imputaciones en una hoja de tiempo ya enviada o aprobada",
        )


# ── Timer ──────────────────────────────────────────────────────────────────────

def compute_timer_elapsed(timer) -> int:
    """Return active (non-paused) elapsed seconds for a TimerSession."""
    now = datetime.now(timezone.utc)
    started = timer.started_at
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    paused_duration = timer.paused_duration_secs or 0
    if timer.paused_at:
        paused_at = timer.paused_at if timer.paused_at.tzinfo else timer.paused_at.replace(tzinfo=timezone.utc)
        total_elapsed = max(0, int((paused_at - started).total_seconds()) - paused_duration)
    else:
        total_elapsed = max(0, int((now - started).total_seconds()) - paused_duration)
    return total_elapsed


def start_timer_session(payload, current_user: User, db: Session):

    existing = db.query(TimerSession).filter(
        and_(TimerSession.user_id == current_user.id, TimerSession.ended_at == None)
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="User already has an active timer")

    if not current_user.hourly_rate or current_user.hourly_rate <= 0:
        raise HTTPException(
            status_code=400,
            detail="No puedes iniciar el cronómetro sin tener una tarifa horaria asignada. Contacta con Recursos Humanos.",
        )

    project = db.query(Project).filter(Project.id == payload.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")

    task = None
    if payload.task_id:
        task = db.query(Task).filter(Task.id == payload.task_id, Task.project_id == payload.project_id).first()
        if not task:
            raise HTTPException(status_code=404, detail="Tarea no encontrada o no pertenece al proyecto")

    # Project membership guard (same rules as validate_and_create_imputation)
    _assert_project_membership(project, task, current_user, db)

    # Additional check: timer on a task requires being the assignee
    if task and current_user.role != UserRole.admin and task.assignee_id != current_user.id:
        raise HTTPException(status_code=403, detail="No puedes iniciar el cronómetro en una tarea que no está asignada a ti.")

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
    return timer


def pause_timer_session(current_user: User, db: Session):

    timer = db.query(TimerSession).filter(
        and_(TimerSession.user_id == current_user.id, TimerSession.ended_at == None)
    ).first()
    if not timer:
        raise HTTPException(status_code=404, detail="No active timer found")

    timer.paused_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(timer)
    return timer


def resume_timer_session(current_user: User, db: Session):

    timer = db.query(TimerSession).filter(
        and_(
            TimerSession.user_id == current_user.id,
            TimerSession.ended_at == None,
            TimerSession.paused_at != None,
        )
    ).first()
    if not timer:
        raise HTTPException(status_code=404, detail="No paused timer found")

    if timer.paused_at:
        paused_at = timer.paused_at if timer.paused_at.tzinfo else timer.paused_at.replace(tzinfo=timezone.utc)
        pause_duration = (datetime.now(timezone.utc) - paused_at).total_seconds()
        timer.paused_duration_secs += int(pause_duration)

    timer.paused_at = None
    db.commit()
    db.refresh(timer)
    return timer


def stop_timer_session(payload, current_user: User, db: Session):
    """Stop timer and create the resulting Imputation. Returns the Imputation."""

    timer = db.query(TimerSession).filter(
        and_(TimerSession.user_id == current_user.id, TimerSession.ended_at == None)
    ).first()
    if not timer:
        raise HTTPException(status_code=404, detail="No active timer found")

    if not current_user.hourly_rate or current_user.hourly_rate <= 0:
        raise HTTPException(
            status_code=400,
            detail="No puedes registrar horas sin tener una tarifa horaria asignada. Contacta con Recursos Humanos.",
        )

    # Re-validate project membership and status at stop time.
    # The user may have been removed from the project, or the project status may
    # have changed since the timer was started.
    project = db.query(Project).filter(Project.id == timer.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="El proyecto asociado ya no existe.")
    if project.status not in (_PS.active, _PS.on_hold, _PS.paused):
        raise HTTPException(
            status_code=400,
            detail=(
                f"El proyecto '{project.name}' está en estado '{project.status.value}' "
                "y no admite nuevas imputaciones."
            ),
        )
    _assert_project_membership(project, None, current_user, db)

    # Re-validate task status if applicable.
    if timer.task_id:
        task = db.query(Task).filter(Task.id == timer.task_id).first()
        if task and task.status in (TaskStatus.done, TaskStatus.cancelled):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"La tarea está en estado '{task.status.value}' "
                    "y no admite nuevas imputaciones."
                ),
            )

    now = datetime.now(timezone.utc)
    started = timer.started_at if timer.started_at.tzinfo else timer.started_at.replace(tzinfo=timezone.utc)
    elapsed = (now - started).total_seconds()
    pause_duration = timer.paused_duration_secs or 0
    if timer.paused_at:
        paused_at = timer.paused_at if timer.paused_at.tzinfo else timer.paused_at.replace(tzinfo=timezone.utc)
        pause_duration += (now - paused_at).total_seconds()
    active_seconds = max(0, elapsed - pause_duration)
    hours = max(0.25, round(active_seconds / 3600, 2))

    # Use the date the timer *started*, not today — timers may span midnight
    imputation_date = started.date()

    # Lockout enforcement (same rules as validate_and_create_imputation)
    if current_user.role != UserRole.admin:
        earliest_allowed = get_lockout_cutoff(current_user, db)
        if imputation_date < earliest_allowed:
            lockout_days = (date.today() - earliest_allowed).days
            raise HTTPException(
                status_code=400,
                detail=(
                    f"No puedes imputar en fechas anteriores a hace {lockout_days} días "
                    f"({earliest_allowed}). El temporizador empezó en una fecha bloqueada."
                ),
            )

    # Daily 24h cap
    existing_hours = db.query(func.sum(Imputation.hours)).filter(
        Imputation.user_id == current_user.id,
        Imputation.date == imputation_date,
    ).scalar() or 0.0
    if existing_hours + hours > 24:
        raise HTTPException(
            status_code=400,
            detail=f"No puedes imputar más de 24h en un día. Ya tienes {existing_hours}h registradas para el {imputation_date}.",
        )

    # Duplicate check (mirrors validate_and_create_imputation)
    if timer.task_id:
        duplicate = db.query(Imputation.id).filter(
            Imputation.user_id == current_user.id,
            Imputation.task_id == timer.task_id,
            Imputation.date == imputation_date,
        ).first()
        if duplicate:
            raise HTTPException(status_code=409, detail="Ya existe una imputación para esta tarea en esa fecha.")
    else:
        duplicate = db.query(Imputation.id).filter(
            Imputation.user_id == current_user.id,
            Imputation.project_id == timer.project_id,
            Imputation.task_id.is_(None),
            Imputation.date == imputation_date,
        ).first()
        if duplicate:
            raise HTTPException(status_code=409, detail="Ya existe una imputación sin tarea para este proyecto en esa fecha.")

    imputation = Imputation(
        user_id=current_user.id,
        task_id=timer.task_id,
        project_id=timer.project_id,
        date=imputation_date,
        hours=hours,
        description=payload.description,
        is_billable=payload.is_billable,
        hourly_rate_snapshot=current_user.hourly_rate,
        cost_amount=round((current_user.hourly_rate or 0) * hours, 2),
        timer_session_id=timer.id,
    )
    db.add(imputation)
    db.flush()

    timer.imputation_id = imputation.id
    timer.ended_at = datetime.now(timezone.utc)
    db.commit()

    imputation = db.query(Imputation).options(
        joinedload(Imputation.user),
        joinedload(Imputation.task),
        joinedload(Imputation.project),
    ).filter(Imputation.id == imputation.id).first()
    return imputation


# ── Week summary ───────────────────────────────────────────────────────────────

def timer_out(timer) -> "TimerSessionOut":
    """Serialize a TimerSession to TimerSessionOut."""
    elapsed = compute_timer_elapsed(timer)
    started = timer.started_at
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    return TimerSessionOut(
        id=timer.id,
        user_id=timer.user_id,
        task_id=timer.task_id,
        project_id=timer.project_id,
        started_at=started.isoformat(),
        paused_at=timer.paused_at,
        paused_duration_secs=timer.paused_duration_secs or 0,
        ended_at=timer.ended_at,
        total_elapsed_seconds=elapsed,
    )


def get_current_timer_record(db: Session, current_user: User):
    """Return the active (non-ended) TimerSession for the user, or None."""
    return db.query(TimerSession).filter(
        and_(
            TimerSession.user_id == current_user.id,
            TimerSession.ended_at == None,
        )
    ).first()


def update_imputation_fields(imp, payload, db: Session):
    """Apply field updates from payload and recompute cost if hours changed. Commits. Valida límites diarios y semanales."""
    from app.models.user import User as UserModel
    from app.models.imputation import Imputation
    from sqlalchemy import func, and_
    from datetime import timedelta
    from fastapi import HTTPException

    # Obtener usuario actual de la imputación
    user = db.query(UserModel).filter(UserModel.id == imp.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado para la imputación")

    # Si se va a cambiar horas, validar límites
    new_hours = payload.hours if payload.hours is not None else imp.hours
    imputation_date = imp.date
    # Límite diario: sumar todas las imputaciones del usuario ese día, excepto la actual
    existing_hours = db.query(func.sum(Imputation.hours)).filter(
        Imputation.user_id == user.id,
        Imputation.date == imputation_date,
        Imputation.id != imp.id
    ).scalar() or 0.0
    if existing_hours + new_hours > 24:
        raise HTTPException(
            status_code=400,
            detail=f"No puedes imputar más de 24h en un día. Ya tienes {existing_hours}h registradas para el {imputation_date}."
        )

    # Límite semanal: sumar todas las imputaciones del usuario esa semana, excepto la actual
    week_start = imputation_date - timedelta(days=imputation_date.weekday())
    week_end = week_start + timedelta(days=6)
    weekly_hours = db.query(func.sum(Imputation.hours)).filter(
        and_(
            Imputation.user_id == user.id,
            Imputation.date >= week_start,
            Imputation.date <= week_end,
            Imputation.id != imp.id
        )
    ).scalar() or 0.0
    weekly_capacity = user.weekly_capacity_hours or 40.0
    if weekly_hours + new_hours > weekly_capacity:
        raise HTTPException(
            status_code=400,
            detail=f"Excederías la capacidad semanal ({weekly_capacity}h). Semana actual: {weekly_hours}h, nueva imputación: {new_hours}h."
        )

    # Aplicar cambios
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(imp, field, value)
    if payload.hours is not None:
        rate = imp.hourly_rate_snapshot
        if rate is not None and rate > 0:
            imp.cost_amount = round(rate * payload.hours, 2)
    db.commit()
    db.refresh(imp)
    return imp


def lockout_status_payload(current_user: User, db: Session):
    """Return LockoutStatusOut for the current user."""
    lockout_cutoff = get_lockout_cutoff(current_user, db)
    today = date.today()
    lockout_days = (today - lockout_cutoff).days
    return LockoutStatusOut(
        lockout_days=lockout_days,
        current_date=today,
        lockout_cutoff_date=lockout_cutoff,
        locked_date_ranges=[],
        editable_date_ranges=[],
    )


def list_alerts_payload(db: Session, current_user: User, acknowledged: bool) -> list:
    """Return ImputationAlertOut list for the current user."""
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


def dismiss_alert_record(db: Session, alert_id: str, current_user: User) -> dict:
    """Dismiss an imputation alert. Raises 404/403 on violations."""
    alert = db.query(ImputationAlert).filter(ImputationAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    if alert.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Cannot dismiss another user's alert")
    alert.dismissed_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": "dismissed"}


def get_week_summary(week_start: Optional[date], current_user: User, db: Session) -> dict:

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

    by_project: dict = {}
    for imp in imputations:
        pid = imp.project_id
        if pid not in by_project:
            by_project[pid] = {
                "project_id": pid,
                "project_name": imp.project.name if imp.project else "?",
                "hours": 0,
            }
        by_project[pid]["hours"] += imp.hours

    by_day: dict = {}
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


def list_imputations_query(
    db: Session,
    current_user: User,
    user_id: Optional[str],
    project_id: Optional[str],
    task_id: Optional[str],
    date_from: Optional[date],
    date_to: Optional[date],
    page: int,
    page_size: int,
):

    q = db.query(Imputation)

    # Scope: employees and subcontractors only see their own imputations
    if current_user.role in ("employee", "subcontractor"):
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

    # Org scoping for non-superadmins
    if current_user.organization_id:
        org_user_ids = db.query(UserModel.id).filter(
            UserModel.organization_id == current_user.organization_id
        ).scalar_subquery()
        q = q.filter(Imputation.user_id.in_(org_user_ids))

    total = q.count()
    items = q.order_by(Imputation.date.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return total, items


def get_imputation_by_id(db: Session, imputation_id: str):
    return db.query(Imputation).filter(Imputation.id == imputation_id).first()


def delete_imputation_record(db: Session, imp) -> None:
    db.delete(imp)
    db.commit()
