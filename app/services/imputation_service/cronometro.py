"""Cronometro de imputacion: arrancar, pausar, reanudar, cancelar y parar.

Parte de `app.services.imputation_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional
from sqlalchemy import func, and_
from sqlalchemy.orm import Session, joinedload
from app.core.timeutil import today_for_user
from app.models.user import User, UserRole
from app.models.imputation import Imputation
from app.models.imputation import TimerSession
from app.models.project import Project, ProjectStatus as _PS
from app.models.task import Task, TaskStatus
from app.schemas.time_tracking import TimerSessionOut
from app.core.errores import ErrorDeDominio
# ── Cost ───────────────────────────────────────────────────────────────────────
import app.services.cost_service as _cost_svc

from app.services.imputation_service._comun import (
    _assert_project_membership,
    _notify_duplicate_imputation_manager,
    get_lockout_cutoff,
    resolve_user_rate,
    sync_imputation_week_timesheet,
)


def _resolve_timer_stop_task(payload, timer: TimerSession, db: Session) -> Optional[Task]:
    task_id_provided = "task_id" in getattr(payload, "model_fields_set", set())
    selected_task_id = payload.task_id if task_id_provided else timer.task_id
    if not selected_task_id:
        return None

    task = db.query(Task).filter(
        Task.id == selected_task_id,
        Task.project_id == timer.project_id,
    ).first()
    if not task:
        raise ErrorDeDominio(status_code=404, detail="Tarea no encontrada o no pertenece al proyecto")
    if task.status in (TaskStatus.done, TaskStatus.cancelled):
        raise ErrorDeDominio(
            status_code=400,
            detail=(
                f"La tarea '{task.title or task.id}' está en estado '{task.status.value}' "
                "y no admite nuevas imputaciones."
            ),
        )
    return task


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
        raise ErrorDeDominio(status_code=409, detail="User already has an active timer")

    if not resolve_user_rate(db, current_user):
        raise ErrorDeDominio(
            status_code=400,
            detail="No puedes iniciar el cronómetro sin tener una tarifa horaria asignada. Contacta con Recursos Humanos.",
        )

    # Audit #62 — org-scoped project lookup
    project_q = db.query(Project).filter(Project.id == payload.project_id)
    if not getattr(current_user, "is_superadmin", False) and current_user.organization_id:
        project_q = project_q.filter(Project.organization_id == current_user.organization_id)
    project = project_q.first()
    if not project:
        raise ErrorDeDominio(status_code=404, detail="Proyecto no encontrado")

    task = None
    if payload.task_id:
        task = db.query(Task).filter(Task.id == payload.task_id, Task.project_id == payload.project_id).first()
        if not task:
            raise ErrorDeDominio(status_code=404, detail="Tarea no encontrada o no pertenece al proyecto")

    # Project membership guard (same rules as validate_and_create_imputation)
    _assert_project_membership(project, task, current_user, db)

    # Additional check: timer on a task requires being the assignee
    if task and current_user.role != UserRole.admin and task.assignee_id != current_user.id:
        raise ErrorDeDominio(status_code=403, detail="No puedes iniciar el cronómetro en una tarea que no está asignada a ti.")

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
        raise ErrorDeDominio(status_code=404, detail="No active timer found")

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
        raise ErrorDeDominio(status_code=404, detail="No paused timer found")

    if timer.paused_at:
        paused_at = timer.paused_at if timer.paused_at.tzinfo else timer.paused_at.replace(tzinfo=timezone.utc)
        pause_duration = (datetime.now(timezone.utc) - paused_at).total_seconds()
        timer.paused_duration_secs += int(pause_duration)

    timer.paused_at = None
    db.commit()
    db.refresh(timer)
    return timer


def cancel_timer_session(current_user: User, db: Session):
    timer = db.query(TimerSession).filter(
        and_(TimerSession.user_id == current_user.id, TimerSession.ended_at == None)
    ).first()
    if not timer:
        raise ErrorDeDominio(status_code=404, detail="No active timer found")

    db.delete(timer)
    db.commit()
    return {"message": "Cronómetro cancelado"}


def _proyecto_valido_para_parar(timer, current_user: User, db: Session):
    """El proyecto del cronómetro, comprobado **al parar** y no al arrancar.

    La revalidación no es paranoia: entre que alguien arranca el cronómetro y lo
    para pueden pasar horas, y en ese rato le pueden haber sacado del proyecto o
    el proyecto puede haberse cerrado. Imputar contra un proyecto cerrado es
    exactamente lo que el control de estados existe para impedir.

    La tarifa se comprueba aquí por el mismo motivo que en el alta manual: sin
    tarifa la imputación no se puede valorar, y una hora sin coste contamina
    todos los informes de rentabilidad en silencio.
    """
    if not resolve_user_rate(db, current_user):
        raise ErrorDeDominio(
            status_code=400,
            detail="No puedes registrar horas sin tener una tarifa horaria asignada. Contacta con Recursos Humanos.",
        )

    project = db.query(Project).filter(Project.id == timer.project_id).first()
    if not project:
        raise ErrorDeDominio(status_code=404, detail="El proyecto asociado ya no existe.")
    if project.status not in (_PS.active, _PS.on_hold, _PS.paused):
        raise ErrorDeDominio(
            status_code=400,
            detail=(
                f"El proyecto '{project.name}' está en estado '{project.status.value}' "
                "y no admite nuevas imputaciones."
            ),
        )
    return project


def _horas_del_cronometro(timer) -> tuple[float, "date"]:
    """Las horas trabajadas y la fecha a la que se imputan.

    Tres sutilezas que estaban sueltas dentro del cuerpo principal y que aquí
    quedan juntas con su razón:

    * **las pausas se descuentan**, incluida la que siga abierta al parar —si
      alguien pausa y se va a casa, ese tiempo no es trabajo;
    * **la fecha es la de inicio, no la de hoy**: un cronómetro que cruza la
      medianoche pertenece al día en que se empezó a trabajar, y si no, el
      trabajo de la noche del viernes aparecería el sábado;
    * **el mínimo es un cuarto de hora**. Un cronómetro de tres minutos se
      registra como 0,25: por debajo de eso el dato no dice nada y ensucia los
      informes con filas de cero.

    El apaño de `tzinfo` es para las filas guardadas antes de que las fechas
    llevaran zona: restarle a un `datetime` con zona uno sin ella revienta.
    """
    ahora = datetime.now(timezone.utc)
    inicio = (timer.started_at if timer.started_at.tzinfo
              else timer.started_at.replace(tzinfo=timezone.utc))

    transcurrido = (ahora - inicio).total_seconds()
    pausado = timer.paused_duration_secs or 0
    if timer.paused_at:
        desde = (timer.paused_at if timer.paused_at.tzinfo
                 else timer.paused_at.replace(tzinfo=timezone.utc))
        pausado += (ahora - desde).total_seconds()

    segundos_activos = max(0, transcurrido - pausado)
    return max(0.25, round(segundos_activos / 3600, 2)), inicio.date()


def _comprobar_cierre_y_tope_diario(current_user: User, db: Session,
                                    fecha, horas: float) -> None:
    """Las dos guardas que comparte con el alta manual: cierre de periodo y 24h.

    Están aquí y no en línea porque son **las mismas reglas** que aplica
    `validate_and_create_imputation`, y tenerlas en dos sitios era pedirle a
    alguien que se acordara de cambiarlas en los dos. El mensaje de cierre sí
    cambia —dice que fue el temporizador el que empezó en fecha bloqueada—
    porque el usuario no eligió esa fecha y conviene que lo sepa.

    El tope de 24 h se calcula sobre lo ya registrado ese día: un cronómetro que
    se quedó corriendo toda la noche no puede meter 30 horas en una jornada.
    """
    if current_user.role != UserRole.admin:
        minima = get_lockout_cutoff(current_user, db)
        if fecha < minima:
            dias = (today_for_user(current_user) - minima).days
            raise ErrorDeDominio(
                status_code=400,
                detail=(
                    f"No puedes imputar en fechas anteriores a hace {dias} días "
                    f"({minima}). El temporizador empezó en una fecha bloqueada."
                ),
            )

    ya_registradas = db.query(func.sum(Imputation.hours)).filter(
        Imputation.user_id == current_user.id,
        Imputation.date == fecha,
    ).scalar() or 0.0
    if ya_registradas + horas > 24:
        raise ErrorDeDominio(
            status_code=400,
            detail=(f"No puedes imputar más de 24h en un día. Ya tienes "
                    f"{ya_registradas}h registradas para el {fecha}."),
        )


def stop_timer_session(payload, current_user: User, db: Session):
    """Stop timer and create the resulting Imputation. Returns the Imputation."""

    timer = db.query(TimerSession).filter(
        and_(TimerSession.user_id == current_user.id, TimerSession.ended_at == None)
    ).first()
    if not timer:
        raise ErrorDeDominio(status_code=404, detail="No active timer found")

    project = _proyecto_valido_para_parar(timer, current_user, db)
    task = _resolve_timer_stop_task(payload, timer, db)
    selected_task_id = task.id if task else None
    _assert_project_membership(project, task, current_user, db)

    hours, imputation_date = _horas_del_cronometro(timer)

    _comprobar_cierre_y_tope_diario(current_user, db, imputation_date, hours)

    # Duplicate check (mirrors validate_and_create_imputation)
    duplicate_imputation_id = None
    if selected_task_id:
        duplicate = db.query(Imputation.id).filter(
            Imputation.user_id == current_user.id,
            Imputation.task_id == selected_task_id,
            Imputation.date == imputation_date,
        ).first()
        if duplicate:
            duplicate_imputation_id = duplicate[0]
            if not payload.force_duplicate:
                raise ErrorDeDominio(status_code=409, detail="Ya existe una imputación para esta tarea en esa fecha.")
    else:
        duplicate = db.query(Imputation.id).filter(
            Imputation.user_id == current_user.id,
            Imputation.project_id == timer.project_id,
            Imputation.task_id.is_(None),
            Imputation.date == imputation_date,
        ).first()
        if duplicate:
            duplicate_imputation_id = duplicate[0]
            if not payload.force_duplicate:
                raise ErrorDeDominio(status_code=409, detail="Ya existe una imputación sin tarea para este proyecto en esa fecha.")

    timer_rate = resolve_user_rate(db, current_user, imputation_date)
    imputation = Imputation(
        user_id=current_user.id,
        task_id=selected_task_id,
        project_id=timer.project_id,
        date=imputation_date,
        hours=hours,
        description=payload.description,
        is_billable=payload.is_billable,
        hourly_rate_snapshot=timer_rate,
        cost_amount=_cost_svc.cost_amount(db, current_user, hours, imputation_date),
        timer_session_id=timer.id,
    )
    db.add(imputation)
    db.flush()

    timer.imputation_id = imputation.id
    timer.ended_at = datetime.now(timezone.utc)

    if duplicate_imputation_id and payload.force_duplicate:
        _notify_duplicate_imputation_manager(
            db,
            current_user,
            project,
            task,
            imputation,
            duplicate_imputation_id,
        )

    db.commit()
    sync_imputation_week_timesheet(db, imputation.user_id, imputation.date)

    imputation = db.query(Imputation).options(
        joinedload(Imputation.user),
        joinedload(Imputation.task),
        joinedload(Imputation.project),
    ).filter(Imputation.id == imputation.id, Imputation.is_active == True).first()
    return imputation


# ── Week summary ───────────────────────────────────────────────────────────────

def timer_out(timer) -> "TimerSessionOut":
    """Serialize a TimerSession to TimerSessionOut."""
    elapsed = compute_timer_elapsed(timer)
    started = timer.started_at
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    task_name = None
    if getattr(timer, "task", None):
        task_name = timer.task.title or getattr(timer.task, "name", None)
    return TimerSessionOut(
        id=timer.id,
        user_id=timer.user_id,
        task_id=timer.task_id,
        task_name=task_name,
        project_id=timer.project_id,
        project_name=getattr(getattr(timer, "project", None), "name", None),
        started_at=started.isoformat(),
        paused_at=timer.paused_at,
        paused_duration_secs=timer.paused_duration_secs or 0,
        ended_at=timer.ended_at,
        total_elapsed_seconds=elapsed,
    )


def get_current_timer_record(db: Session, current_user: User):
    """Return the active (non-ended) TimerSession for the user, or None."""
    return db.query(TimerSession).options(
        joinedload(TimerSession.project),
        joinedload(TimerSession.task),
    ).filter(
        and_(
            TimerSession.user_id == current_user.id,
            TimerSession.ended_at == None,
        )
    ).first()
