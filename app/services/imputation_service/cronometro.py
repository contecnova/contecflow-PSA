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
from app.core.codigos_de_error import error


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
        raise error(404, "tarea_no_en_proyecto")
    if task.status in (TaskStatus.done, TaskStatus.cancelled):
        raise error(400, "imputar_tarea_estado", detail=f"La tarea '{task.title or task.id}' está en estado '{task.status.value}' "
                "y no admite nuevas imputaciones.", tarea=task.title or task.id, estado=task.status.value)
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

    # M31 (auditoría 22-11-2026): la comprobación de «ya hay uno activo» se
    # serializa por persona (dos clics a la vez creaban dos cronómetros).
    from app.db.session import is_postgres
    if is_postgres():
        from sqlalchemy import text
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"cronometro:{current_user.id}"})
    existing = db.query(TimerSession).filter(
        and_(TimerSession.user_id == current_user.id, TimerSession.ended_at == None)
    ).first()
    if existing:
        raise error(409, "cronometro_ya_activo", detail="User already has an active timer")

    if not resolve_user_rate(db, current_user):
        raise error(400, "sin_tarifa_horaria", detail="No puedes iniciar el cronómetro sin tener una tarifa horaria asignada. Contacta con Recursos Humanos.")

    # Audit #62 — org-scoped project lookup
    project_q = db.query(Project).filter(Project.id == payload.project_id)
    if not getattr(current_user, "is_superadmin", False) and current_user.organization_id:
        project_q = project_q.filter(Project.organization_id == current_user.organization_id)
    project = project_q.first()
    if not project:
        raise error(404, "no_encontrado", detail="Proyecto no encontrado", que="proyecto")

    task = None
    if payload.task_id:
        task = db.query(Task).filter(Task.id == payload.task_id, Task.project_id == payload.project_id).first()
        if not task:
            raise error(404, "tarea_no_en_proyecto")

    # Project membership guard (same rules as validate_and_create_imputation)
    _assert_project_membership(project, task, current_user, db)

    # Additional check: timer on a task requires being the assignee
    if task and current_user.role != UserRole.admin and task.assignee_id != current_user.id:
        raise error(403, "cronometro_tarea_no_asignada")

    now = datetime.now(timezone.utc)
    timer = TimerSession(
        user_id=current_user.id,
        task_id=payload.task_id,
        project_id=payload.project_id,
        started_at=now,
    )
    db.add(timer)
    # Migración 201: el índice único parcial (un cronómetro abierto por persona)
    # para la carrera que el bloqueo de arriba no cubre (SQLite, otro proceso):
    # el choque es un 409 con código, nunca un 500.
    from sqlalchemy.exc import IntegrityError
    try:
        db.flush()
        db.commit()
    except IntegrityError:
        db.rollback()
        raise error(409, "cronometro_ya_activo", detail="User already has an active timer")
    db.refresh(timer)
    return timer


def pause_timer_session(current_user: User, db: Session):

    timer = db.query(TimerSession).filter(
        and_(TimerSession.user_id == current_user.id, TimerSession.ended_at == None)
    ).first()
    if not timer:
        raise error(404, "cronometro_sin_activo", detail="No active timer found")

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
        raise error(404, "cronometro_sin_activo", detail="No paused timer found")

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
        raise error(404, "cronometro_sin_activo", detail="No active timer found")

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
        raise error(400, "sin_tarifa_horaria", detail="No puedes registrar horas sin tener una tarifa horaria asignada. Contacta con Recursos Humanos.")

    project = db.query(Project).filter(Project.id == timer.project_id).first()
    if not project:
        raise error(404, "no_encontrado", detail="El proyecto asociado ya no existe.", que="proyecto")
    if project.status not in (_PS.active, _PS.on_hold, _PS.paused):
        raise error(400, "imputar_proyecto_estado", detail=f"El proyecto '{project.name}' está en estado '{project.status.value}' "
                "y no admite nuevas imputaciones.", proyecto=project.name, estado=project.status.value)
    return project


def _horas_del_cronometro(timer, usuario=None) -> tuple[float, "date"]:
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
    # Auditoría 22-11-2026 (A47): el día de inicio en la zona de la persona
    # (antes, en UTC: la tarde en América o la madrugada en Asia caían en otro día).
    if usuario is not None:
        from app.core.timeutil import zone_for_user
        dia = inicio.astimezone(zone_for_user(usuario)).date()
    else:
        dia = inicio.date()
    return max(0.25, round(segundos_activos / 3600, 2)), dia


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
            raise error(400, "imputar_fecha_bloqueada_cronometro", dias=dias, fecha=minima)

    ya_registradas = db.query(func.sum(Imputation.hours)).filter(
        Imputation.user_id == current_user.id,
        Imputation.date == fecha,
        Imputation.is_active.is_(True),   # A45: sin contar las borradas
    ).scalar() or 0.0
    if ya_registradas + horas > 24:
        raise error(400, "imputar_mas_de_24h", detail=f"No puedes imputar más de 24h en un día. Ya tienes "
                    f"{ya_registradas}h registradas para el {fecha}.", horas=ya_registradas)


def stop_timer_session(payload, current_user: User, db: Session):
    """Stop timer and create the resulting Imputation. Returns the Imputation."""

    timer = db.query(TimerSession).filter(
        and_(TimerSession.user_id == current_user.id, TimerSession.ended_at == None)
    ).first()
    if not timer:
        raise error(404, "cronometro_sin_activo", detail="No active timer found")

    project = _proyecto_valido_para_parar(timer, current_user, db)
    task = _resolve_timer_stop_task(payload, timer, db)
    selected_task_id = task.id if task else None
    _assert_project_membership(project, task, current_user, db)

    hours, imputation_date = _horas_del_cronometro(timer, current_user)
    # M31 (auditoría 22-11-2026): un cronómetro olvidado (más de 24 h) ya no
    # queda imposible de parar: se paran con las horas reales (`hours`, como
    # mucho las medidas), como en las herramientas de control horario del mercado.
    reales = getattr(payload, "hours", None)
    if reales:
        hours = round(min(float(reales), hours), 2)
    elif hours > 24:
        raise error(422, "cronometro_demasiado_largo", horas=24)

    _comprobar_cierre_y_tope_diario(current_user, db, imputation_date, hours)

    # Auditoría 22-11-2026 (A48): el resto de reglas (duplicados, tope semanal,
    # control de horas extra «bloquear», estado de la tarea…) son las del alta
    # manual, por la misma puerta. Antes el cronómetro las esquivaba.
    from app.services.imputation_service.alta import crear_imputacion_validada

    def _cerrar_cronometro(imp) -> None:
        imp.timer_session_id = timer.id
        timer.imputation_id = imp.id
        timer.ended_at = datetime.now(timezone.utc)

    imputation = crear_imputacion_validada(
        current_user, db, project_id=timer.project_id, fecha=imputation_date, horas=hours,
        task_id=selected_task_id, description=payload.description, is_billable=payload.is_billable,
        force_duplicate=bool(getattr(payload, "force_duplicate", False)),
        antes_de_confirmar=_cerrar_cronometro,
    )

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
