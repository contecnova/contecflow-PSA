"""
imputation_service.py — Lógica de negocio para imputaciones y cronómetros.

Funciones exportadas:
  compute_cost(user, hours, db=None, on_date=None)
  resolve_user_rate(db, user, on_date=None)
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
from app.core.timeutil import today_for_user
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
from app.services.notifications import notify_user
from app.services.psa_flows import sync_timesheet_from_imputations_flow
from fastapi import HTTPException


# ── Cost ───────────────────────────────────────────────────────────────────────
import app.services.cost_service as _cost_svc
from app.core import timeutil


def resolve_user_rate(db: Session, user: User, on_date: Optional[date] = None) -> float:
    """Cost per hour for `user` on `on_date`. Versioned UserCostProfile takes precedence,
    legacy `User.hourly_rate` is the fallback. Returns 0.0 when neither has data."""
    return _cost_svc.cost_per_hour(db, user, on_date) or 0.0


def compute_cost(user: User, hours: float, db: Optional[Session] = None,
                 on_date: Optional[date] = None) -> float:
    """Compute cost for the given user and hours using the canonical cost service.

    A db session is required to consult versioned cost profiles; callers without
    one fall back to `user.hourly_rate` for backward compatibility.
    """
    if db is None:
        base_rate = user.hourly_rate or 0.0
        return round(base_rate * hours, 2)
    return _cost_svc.cost_amount(db, user, hours, on_date)


def sync_imputation_week_timesheet(db: Session, user_id: str, work_date: date) -> Timesheet:
    week_start = work_date - timedelta(days=work_date.weekday())
    return sync_timesheet_from_imputations_flow(db, user_id, week_start)


# ── Lockout ────────────────────────────────────────────────────────────────────

def _dias_de_bloqueo(db: Session, org_id) -> int:
    """El ajuste de Admin (revisión 2026-11): antes se leía el del fichero."""
    from app.services.settings_service import get_runtime_int
    return int(get_runtime_int(db, "DEFAULT_IMPUTATION_LOCKOUT_DAYS", org_id))


def get_lockout_cutoff(current_user: User, db: Session) -> date:
    org = None
    if current_user.organization_id:
        org = db.query(Organization).filter(
            Organization.id == current_user.organization_id
        ).first()
    lockout_days = _dias_de_bloqueo(db, current_user.organization_id)
    # El día de corte se calcula en la zona del usuario (auditoría 2026-08,
    # hallazgo 14). Con `timeutil.today()` lo decidía la zona del servidor: un
    # empleado en México a las 23:30 del día 28 veía el corte del día 29 del
    # servidor, así que podía perder un día completo de plazo para imputar.
    return today_for_user(current_user, org) - timedelta(days=lockout_days)


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
        raise HTTPException(status_code=404, detail="Tarea no encontrada o no pertenece al proyecto")
    if task.status in (TaskStatus.done, TaskStatus.cancelled):
        raise HTTPException(
            status_code=400,
            detail=(
                f"La tarea '{task.title or task.id}' está en estado '{task.status.value}' "
                "y no admite nuevas imputaciones."
            ),
        )
    return task


def _notify_duplicate_imputation_manager(
    db: Session,
    current_user: User,
    project: Project,
    task: Optional[Task],
    imputation: Imputation,
    duplicate_imputation_id: Optional[str],
) -> None:
    manager_id = None
    if current_user.manager_id and current_user.manager_id != current_user.id:
        manager_id = current_user.manager_id
    elif project.pm_id and project.pm_id != current_user.id:
        manager_id = project.pm_id

    if not manager_id:
        return

    task_label = task.title if task and task.title else "sin tarea"
    body = (
        f"{current_user.full_name} forzó el cierre de un cronómetro con una imputación duplicada "
        f"para {project.name} · {task_label} el {imputation.date}. "
        f"Se registraron {imputation.hours}h."
    )
    if duplicate_imputation_id:
        body += f" Ya existía la imputación {duplicate_imputation_id}."
    body += " Revisa el timesheet si quieres rechazarla."

    notify_user(
        db,
        manager_id,
        "system",
        "Imputación forzada pendiente de revisión",
        body,
        resource="imputations",
        resource_id=imputation.id,
        action_url="/time",
    )


# ── Validate & create ──────────────────────────────────────────────────────────

# ── Alta de una imputacion: las reglas de negocio ────────────────────────────
#
# Auditoria 2026-08 (hallazgo 18). `validate_and_create_imputation` era
# complejidad 20 en nueve reglas encadenadas. Cada regla es ahora una funcion con
# nombre, y el orquestador se lee como la lista ordenada de reglas.
#
# EL ORDEN ES PARTE DEL CONTRATO, no una casualidad de como se escribio: decide
# QUE error ve la persona cuando incumple dos reglas a la vez. El original ya lo
# decia en un comentario para una de ellas («Daily cap — checked before duplicate
# so exceeding 24h always returns 400»); aqui se conserva entero y hay un test
# (`test_imputation_orden_de_validaciones`) que lo fija.


def _validar_fecha_imputable(payload, current_user: User, db: Session) -> None:
    """Ni antes del cierre de periodo ni en el futuro.

    Los administradores quedan exentos a proposito: son quienes corrigen
    historico, y bloquearles la correccion dejaria los errores sin arreglar.
    """
    if current_user.role == UserRole.admin:
        return

    earliest_allowed = get_lockout_cutoff(current_user, db)
    if payload.date < earliest_allowed:
        lockout_days = (today_for_user(current_user) - earliest_allowed).days
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


def _buscar_proyecto_del_usuario(payload, current_user: User, db: Session) -> Project:
    """El proyecto, acotado a la organizacion de quien imputa.

    Auditoria #62: sin el filtro por organizacion, un ID adivinado servia para
    saber si un proyecto de otro cliente existe. Se devuelve 404 —y no 403— para
    no confirmar su existencia.
    """
    project_q = db.query(Project).filter(Project.id == payload.project_id)
    if not getattr(current_user, "is_superadmin", False) and current_user.organization_id:
        project_q = project_q.filter(Project.organization_id == current_user.organization_id)
    project = project_q.first()
    if not project:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    return project


def _buscar_tarea_del_proyecto(payload, db: Session) -> Optional[Task]:
    """La tarea, si se indica, comprobando que pertenece a ese proyecto.

    El filtro por `project_id` es lo que impide imputar a la tarea de un
    proyecto distinto del que se declara.
    """
    if not payload.task_id:
        return None
    task = db.query(Task).filter(
        Task.id == payload.task_id,
        Task.project_id == payload.project_id,
    ).first()
    if not task:
        raise HTTPException(
            status_code=404, detail="Tarea no encontrada o no pertenece al proyecto"
        )
    return task


def _validar_estado_del_proyecto(project: Project) -> None:
    """Un proyecto cerrado no admite horas nuevas."""
    if project.status in (_PS.completed, _PS.closed, _PS.cancelled, _PS.archived):
        raise HTTPException(
            status_code=400,
            detail=f"No puedes imputar horas a un proyecto en estado '{project.status}'. Contacta con el PM si necesitas registrar horas históricas.",
        )


def _validar_tarifa_horaria(payload, current_user: User, db: Session) -> None:
    """Sin tarifa no se puede imputar: la hora no se podria costear.

    Los subcontratistas quedan exentos porque su coste no sale de una tarifa
    interna sino de su factura.
    """
    if (not resolve_user_rate(db, current_user, payload.date)) and current_user.role != UserRole.subcontractor:
        raise HTTPException(
            status_code=400,
            detail="No puedes imputar horas sin tener una tarifa horaria asignada. Contacta con Recursos Humanos.",
        )


def _validar_tope_diario(payload, current_user: User, db: Session) -> None:
    """Nadie imputa mas de 24 h en un dia.

    Va ANTES del control de duplicados a proposito: pasarse de 24 h tiene que
    devolver siempre 400 y no un 409 de duplicado, porque el 409 es recuperable
    (`force_duplicate`) y este no.
    """
    existing_hours = db.query(func.sum(Imputation.hours)).filter(
        Imputation.user_id == current_user.id,
        Imputation.date == payload.date,
    ).scalar() or 0.0
    if existing_hours + payload.hours > 24:
        raise HTTPException(
            status_code=400,
            detail=f"No puedes imputar más de 24h en un día. Ya tienes {existing_hours}h registradas.",
        )


def _validar_estado_de_la_tarea(task: Optional[Task]) -> None:
    """Una tarea acabada o cancelada no admite horas nuevas."""
    if task and task.status in (TaskStatus.done, TaskStatus.cancelled):
        raise HTTPException(
            status_code=400,
            detail=f"No puedes imputar horas en una tarea con estado '{task.status}'.",
        )


def _id_de_imputacion_duplicada(payload, current_user: User, task, db: Session) -> Optional[str]:
    """Comprueba si ya hay una imputacion igual. Devuelve su id si se fuerza.

    Dos caminos porque el indice unico no cubre los dos casos: cuando no hay
    tarea, `task_id` es NULL, y en SQL NULL != NULL, asi que el indice no impide
    el duplicado y hay que comprobarlo aqui a mano.

    Con `force_duplicate` no rechaza: devuelve el id del original para poder
    avisar despues al manager.
    """
    if task:
        fila = db.query(Imputation.id).filter(
            Imputation.user_id == current_user.id,
            Imputation.task_id == payload.task_id,
            Imputation.date == payload.date,
        ).first()
        mensaje = "Ya existe una imputación para esta tarea en esa fecha."
    else:
        fila = db.query(Imputation.id).filter(
            Imputation.user_id == current_user.id,
            Imputation.project_id == payload.project_id,
            Imputation.task_id.is_(None),
            Imputation.date == payload.date,
        ).first()
        mensaje = "Ya existe una imputación sin tarea para este proyecto en esa fecha."

    if not fila:
        return None
    if not getattr(payload, "force_duplicate", False):
        raise HTTPException(status_code=409, detail=mensaje)
    return fila[0]


def _validar_tope_semanal(payload, current_user: User, db: Session) -> None:
    """No se puede pasar de la capacidad semanal de la persona."""
    week_start = payload.date - timedelta(days=payload.date.weekday())
    week_end = week_start + timedelta(days=6)
    weekly_hours = db.query(func.sum(Imputation.hours)).filter(
        and_(
            Imputation.user_id == current_user.id,
            Imputation.date >= week_start,
            Imputation.date <= week_end,
        )
    ).scalar() or 0.0
    weekly_capacity = current_user.weekly_capacity_hours or settings.DEFAULT_WEEKLY_CAPACITY_HOURS
    if weekly_hours + payload.hours > weekly_capacity:
        raise HTTPException(
            status_code=400,
            detail=f"Excederías la capacidad semanal ({weekly_capacity}h). Semana actual: {weekly_hours}h, nueva imputación: {payload.hours}h.",
        )


def _crear_imputacion(payload, current_user: User, db: Session) -> Imputation:
    """Crea el registro con la tarifa CONGELADA en el momento de imputar.

    `hourly_rate_snapshot` no es redundante con la tarifa del usuario: una
    subida de sueldo no debe recalcular el coste de las horas ya imputadas.
    """
    rate = resolve_user_rate(db, current_user, payload.date)
    imputation = Imputation(
        user_id=current_user.id,
        task_id=payload.task_id,
        project_id=payload.project_id,
        date=payload.date,
        hours=payload.hours,
        description=payload.description,
        is_billable=payload.is_billable,
        hourly_rate_snapshot=rate,   # en la moneda del perfil de coste
        # Revisión 2026-11: el coste, siempre en la moneda de la empresa (con el tipo de la fecha).
        # Antes se guardaba en la del perfil y nadie lo convertía.
        cost_amount=_cost_svc.cost_amount(db, current_user, payload.hours, payload.date),
    )
    db.add(imputation)
    try:
        db.flush()
    # intentional: chained re-raise preserves context
    except IntegrityError as exc:
        # La ultima linea de defensa: el indice unico. Se llega aqui cuando dos
        # peticiones simultaneas pasan los dos el control de duplicados.
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Ya existe una imputación para esta tarea en esa fecha.",
        ) from exc
    return imputation


def validate_and_create_imputation(payload, current_user: User, db: Session):
    """
    Validates all business rules and creates an Imputation record.
    Returns the newly created Imputation ORM object.
    Raises HTTPException on any violation.

    El orden de las reglas es parte del contrato: ver la nota de cabecera.
    """
    _validar_fecha_imputable(payload, current_user, db)
    project = _buscar_proyecto_del_usuario(payload, current_user, db)
    task = _buscar_tarea_del_proyecto(payload, db)
    _assert_project_membership(project, task, current_user, db)
    _validar_estado_del_proyecto(project)
    _validar_tarifa_horaria(payload, current_user, db)
    _validar_tope_diario(payload, current_user, db)
    _validar_estado_de_la_tarea(task)
    duplicate_imputation_id = _id_de_imputacion_duplicada(payload, current_user, task, db)
    _validar_tope_semanal(payload, current_user, db)

    imputation = _crear_imputacion(payload, current_user, db)

    if getattr(payload, "force_duplicate", False) and duplicate_imputation_id:
        _notify_duplicate_imputation_manager(
            db,
            current_user,
            project,
            task,
            imputation,
            duplicate_imputation_id,
        )

    db.commit()
    db.refresh(imputation)
    sync_imputation_week_timesheet(db, imputation.user_id, imputation.date)
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
            lockout_days = (today_for_user(current_user) - earliest_allowed).days
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

    if not resolve_user_rate(db, current_user):
        raise HTTPException(
            status_code=400,
            detail="No puedes iniciar el cronómetro sin tener una tarifa horaria asignada. Contacta con Recursos Humanos.",
        )

    # Audit #62 — org-scoped project lookup
    project_q = db.query(Project).filter(Project.id == payload.project_id)
    if not getattr(current_user, "is_superadmin", False) and current_user.organization_id:
        project_q = project_q.filter(Project.organization_id == current_user.organization_id)
    project = project_q.first()
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


def cancel_timer_session(current_user: User, db: Session):
    timer = db.query(TimerSession).filter(
        and_(TimerSession.user_id == current_user.id, TimerSession.ended_at == None)
    ).first()
    if not timer:
        raise HTTPException(status_code=404, detail="No active timer found")

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
        raise HTTPException(
            status_code=400,
            detail="No puedes registrar horas sin tener una tarifa horaria asignada. Contacta con Recursos Humanos.",
        )

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
            raise HTTPException(
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
        raise HTTPException(
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
        raise HTTPException(status_code=404, detail="No active timer found")

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
                raise HTTPException(status_code=409, detail="Ya existe una imputación para esta tarea en esa fecha.")
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
                raise HTTPException(status_code=409, detail="Ya existe una imputación sin tarea para este proyecto en esa fecha.")

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


def update_imputation_fields(imp, payload, db: Session, current_user: User = None):
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

    # G3 Fix: Field-level permissions — restrict critical fields by role
    # Only admin and manager can edit: billable_hours, hourly_rate_snapshot, project_id, task_id
    critical_fields = {"billable_hours", "hourly_rate_snapshot", "project_id", "task_id", "cost_amount"}
    manager_roles = {UserRole.admin, UserRole.pm, UserRole.team_lead, UserRole.hr}
    is_self_non_manager = (
        current_user
        and current_user.id == imp.user_id
        and current_user.role not in manager_roles
    )

    if is_self_non_manager:
        # Non-manager editing own imputation: only allow non-sensitive fields.
        allowed_fields = {"hours", "notes", "body"}
        filtered_payload = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if k in allowed_fields}
        if set(payload.model_dump(exclude_unset=True).keys()) & critical_fields:
            raise HTTPException(status_code=403, detail="No tienes permiso para editar campos críticos de la imputación")
    else:
        filtered_payload = payload.model_dump(exclude_unset=True)

    # Si se va a cambiar horas, validar límites
    new_hours = filtered_payload.get("hours", payload.hours if payload.hours is not None else imp.hours)
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
    weekly_capacity = user.weekly_capacity_hours or settings.DEFAULT_WEEKLY_CAPACITY_HOURS
    if weekly_hours + new_hours > weekly_capacity:
        raise HTTPException(
            status_code=400,
            detail=f"Excederías la capacidad semanal ({weekly_capacity}h). Semana actual: {weekly_hours}h, nueva imputación: {new_hours}h."
        )

    # Aplicar cambios
    horas_antes, coste_antes = imp.hours, imp.cost_amount
    for field, value in filtered_payload.items():
        setattr(imp, field, value)
    if payload.hours is not None:
        # La tarifa y el tipo de cambio quedaron congelados al imputar: el coste escala con las horas.
        if coste_antes is not None and horas_antes:
            imp.cost_amount = round(coste_antes * payload.hours / horas_antes, 2)
        elif imp.hourly_rate_snapshot:
            imp.cost_amount = round(imp.hourly_rate_snapshot * payload.hours, 2)
    db.commit()
    db.refresh(imp)
    sync_imputation_week_timesheet(db, imp.user_id, imp.date)
    return imp


def lockout_status_payload(current_user: User, db: Session):
    """Return LockoutStatusOut for the current user."""
    lockout_cutoff = get_lockout_cutoff(current_user, db)
    today = timeutil.today()
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
        today = timeutil.today()
        week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    imputations = db.query(Imputation).options(
        joinedload(Imputation.project)
    ).filter(
        Imputation.user_id == current_user.id,
        Imputation.date >= week_start,
        Imputation.date <= week_end,
        Imputation.is_active == True,
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

    q = db.query(Imputation).options(
        joinedload(Imputation.user),
        joinedload(Imputation.task),
        joinedload(Imputation.project),
    ).filter(Imputation.is_active == True)

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


def get_imputation_by_id(db: Session, imputation_id: str, current_user: Optional[User] = None):
    """Fetch an imputation by id, optionally scoped to the current user's org.

    Audit #62: When current_user is supplied and is NOT a superadmin, the
    query is restricted to imputations whose author belongs to the same
    organization. Without this filter, an attacker could read imputations
    of another tenant by guessing the id.
    """
    q = db.query(Imputation).options(
        joinedload(Imputation.user),
        joinedload(Imputation.task),
        joinedload(Imputation.project),
    ).filter(Imputation.id == imputation_id, Imputation.is_active == True)
    if current_user is not None and not getattr(current_user, "is_superadmin", False) and current_user.organization_id:
        org_user_ids = db.query(UserModel.id).filter(
            UserModel.organization_id == current_user.organization_id
        ).scalar_subquery()
        q = q.filter(Imputation.user_id.in_(org_user_ids))
    return q.first()


def delete_imputation_record(db: Session, imp) -> None:
    """Soft-delete an imputation."""
    user_id = imp.user_id
    work_date = imp.date
    imp.is_active = False
    db.commit()
    sync_imputation_week_timesheet(db, user_id, work_date)
