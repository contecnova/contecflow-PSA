"""Alta de imputaciones con todas sus validaciones, y si una imputacion se puede editar.

Parte de `app.services.imputation_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy import func, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.services.settings_service.por_empresa import capacidad_semanal
from app.core.timeutil import today_for_user
from app.models.user import User, UserRole
from app.models.financial import Timesheet, TimesheetStatus
from app.models.imputation import Imputation
from app.models.project import Project, ProjectStatus as _PS
from app.models.task import Task, TaskStatus
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
        # M34 (auditoría 22-11-2026): la excepción del administrador queda
        # marcada y se audita aparte (`IMPUTATION_ADMIN_OVERRIDE`) al crear.
        cierre = get_lockout_cutoff(current_user, db)
        if payload.date < cierre or payload.date > today_for_user(current_user):
            try:
                payload._excepcion_admin = "fecha_bloqueada" if payload.date < cierre else "fecha_futura"
            except AttributeError:
                pass
        return

    earliest_allowed = get_lockout_cutoff(current_user, db)
    if payload.date < earliest_allowed:
        lockout_days = (today_for_user(current_user) - earliest_allowed).days
        raise error(400, "imputar_fecha_bloqueada", dias=lockout_days, fecha=earliest_allowed)
    # Auditoría 22-11-2026 (A46): «hoy» en la zona de la persona (antes UTC: en
    # UTC+8 no se podía imputar el día en curso hasta las 08:00).
    if payload.date > today_for_user(current_user):
        raise error(400, "imputar_fecha_futura")


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
        raise error(404, "no_encontrado", detail="Proyecto no encontrado", que="proyecto")
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
        raise error(404, "tarea_no_en_proyecto")
    return task


def _validar_estado_del_proyecto(project: Project) -> None:
    """Un proyecto cerrado no admite horas nuevas."""
    if project.status in (_PS.completed, _PS.closed, _PS.cancelled, _PS.archived):
        raise error(400, "imputar_proyecto_estado", detail=f"No puedes imputar horas a un proyecto en estado '{project.status}'. Contacta con el PM si necesitas registrar horas históricas.", estado=project.status)


def _validar_tarifa_horaria(payload, current_user: User, db: Session) -> None:
    """Sin tarifa no se puede imputar: la hora no se podria costear.

    Los subcontratistas quedan exentos porque su coste no sale de una tarifa
    interna sino de su factura.
    """
    if (not resolve_user_rate(db, current_user, payload.date)) and current_user.role != UserRole.subcontractor:
        raise error(400, "sin_tarifa_horaria")


def _validar_tope_diario(payload, current_user: User, db: Session) -> None:
    """Nadie imputa mas de 24 h en un dia.

    Va ANTES del control de duplicados a proposito: pasarse de 24 h tiene que
    devolver siempre 400 y no un 409 de duplicado, porque el 409 es recuperable
    (`force_duplicate`) y este no.
    """
    # A45: sin contar las borradas (antes daban 400 al volver a imputar).
    existing_hours = db.query(func.sum(Imputation.hours)).filter(
        Imputation.user_id == current_user.id,
        Imputation.date == payload.date,
        Imputation.is_active.is_(True),
    ).scalar() or 0.0
    if existing_hours + payload.hours > 24:
        raise error(400, "imputar_mas_de_24h", horas=existing_hours)


def _validar_estado_de_la_tarea(task: Optional[Task]) -> None:
    """Una tarea acabada o cancelada no admite horas nuevas."""
    if task and task.status in (TaskStatus.done, TaskStatus.cancelled):
        raise error(400, "imputar_tarea_estado", detail=f"No puedes imputar horas en una tarea con estado '{task.status}'.", estado=task.status)


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
            Imputation.is_active.is_(True),
        ).first()
        mensaje = "Ya existe una imputación para esta tarea en esa fecha."
    else:
        fila = db.query(Imputation.id).filter(
            Imputation.user_id == current_user.id,
            Imputation.project_id == payload.project_id,
            Imputation.task_id.is_(None),
            Imputation.date == payload.date,
            Imputation.is_active.is_(True),
        ).first()
        mensaje = "Ya existe una imputación sin tarea para este proyecto en esa fecha."

    if not fila:
        return None
    if not getattr(payload, "force_duplicate", False):
        raise error(409, "imputacion_duplicada", detail=mensaje)
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
            Imputation.is_active.is_(True),
        )
    ).scalar() or 0.0
    weekly_capacity = capacidad_semanal(db, current_user)
    # Horas extra (18-11-2026): lo aprobado amplía el tope; con control «avisar» o
    # «regularizar» el control es el de horas extra, día a día (ver horas_extra/control.py).
    from app.services.horas_extra import control as control_horas_extra
    weekly_capacity += control_horas_extra.capacidad_semanal_extra(db, current_user.id, payload.date)
    if weekly_hours + payload.hours > weekly_capacity:
        raise error(400, "imputar_supera_capacidad", detail=f"Excederías la capacidad semanal ({weekly_capacity}h). Semana actual: {weekly_hours}h, nueva imputación: {payload.hours}h.", capacidad=weekly_capacity, semana=weekly_hours, nueva=payload.hours)


def _crear_imputacion(payload, current_user: User, db: Session) -> Imputation:
    """Crea el registro con la tarifa CONGELADA en el momento de imputar.

    `hourly_rate_snapshot` no es redundante con la tarifa del usuario: una
    subida de sueldo no debe recalcular el coste de las horas ya imputadas.
    """
    rate = resolve_user_rate(db, current_user, payload.date, payload.project_id)
    imputation = Imputation(
        user_id=current_user.id,
        task_id=payload.task_id,
        project_id=payload.project_id,
        date=payload.date,
        hours=payload.hours,
        description=payload.description,
        is_billable=payload.is_billable,
        hourly_rate_snapshot=rate,   # M7: en la moneda de la empresa (cost_per_hour ya convierte)
        # Revisión 2026-11: el coste, siempre en la moneda de la empresa (con el tipo de la fecha).
        # Antes se guardaba en la del perfil y nadie lo convertía.
        cost_amount=_cost_svc.cost_amount(db, current_user, payload.hours, payload.date,
                                          project_id=payload.project_id),
    )
    db.add(imputation)
    try:
        db.flush()
    # intentional: chained re-raise preserves context
    except IntegrityError as exc:
        # La ultima linea de defensa: el indice unico. Se llega aqui cuando dos
        # peticiones simultaneas pasan los dos el control de duplicados.
        db.rollback()
        raise error(409, "imputacion_duplicada") from exc
    return imputation


def _bloquear_dia(db: Session, user_id: str, fecha) -> None:
    """M30: dos altas simultáneas de la misma persona y día se serializan (bloqueo
    de transacción de PostgreSQL), así el control de duplicados y de topes ve la
    otra. No hay índice único posible: un duplicado consciente (`force_duplicate`)
    está permitido."""
    from app.db.session import is_postgres
    if not is_postgres():
        return
    from sqlalchemy import text
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"imputacion:{user_id}:{fecha}"})


def validate_and_create_imputation(payload, current_user: User, db: Session, antes_de_confirmar=None):
    """
    Validates all business rules and creates an Imputation record.
    Returns the newly created Imputation ORM object.
    Raises HTTPException on any violation.

    El orden de las reglas es parte del contrato: ver la nota de cabecera.

    Auditoría 22-11-2026 (A34, A35, A48, A6): es la ÚNICA puerta de alta. El
    cronómetro, Slack, los bots de colaboración y la voz pasan por aquí (con
    `crear_imputacion_validada`), así que todas aplican el cierre de periodo,
    la fecha futura, la pertenencia, la tarifa, los topes diario y semanal,
    los duplicados y el control de horas extra. `antes_de_confirmar(imp)`
    deja a quien llama completar su parte (p. ej. cerrar el cronómetro) en la
    MISMA transacción.
    """
    _bloquear_dia(db, current_user.id, payload.date)
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
    # Horas extra (18-11-2026): con control «bloquear», nada fuera de horario sin autorización.
    from app.services.horas_extra import control as control_horas_extra
    control_horas_extra.antes_de_imputar(db, current_user.id, payload.date, payload.hours)

    imputation = _crear_imputacion(payload, current_user, db)
    if antes_de_confirmar is not None:
        antes_de_confirmar(imputation)

    if getattr(payload, "force_duplicate", False) and duplicate_imputation_id:
        _notify_duplicate_imputation_manager(
            db,
            current_user,
            project,
            task,
            imputation,
            duplicate_imputation_id,
        )

    excepcion = getattr(payload, "_excepcion_admin", None)
    if excepcion:
        from app.services.audit import audit_log
        audit_log(db, current_user, "IMPUTATION_ADMIN_OVERRIDE", "imputations", imputation.id, str(payload.date),
                  new_values={"motivo": excepcion, "fecha": str(payload.date), "horas": payload.hours})
    # M30 (auditoría 22-11-2026): la hoja semanal se recalcula en la MISMA
    # transacción que la imputación (antes, commit y luego otra transacción: si
    # la segunda fallaba, la hoja quedaba desfasada).
    db.flush()
    sync_imputation_week_timesheet(db, imputation.user_id, imputation.date)   # confirma las dos cosas
    db.refresh(imputation)
    # Horas extra: regularizar (declaración posterior) o avisar; nunca deshace la imputación.
    control_horas_extra.despues_de_imputar(db, imputation.user_id, imputation.date, current_user.id)
    return imputation


def crear_imputacion_validada(current_user: User, db: Session, *, project_id: str, fecha, horas: float,
                              task_id: Optional[str] = None, description: Optional[str] = None,
                              is_billable: bool = False, force_duplicate: bool = False,
                              antes_de_confirmar=None) -> Imputation:
    """Alta de imputación desde cualquier vía que no sea el formulario (cronómetro,
    Slack, bots, voz): construye el payload y pasa por `validate_and_create_imputation`.

    Las horas se validan como en el esquema de la API (> 0 y <= 24, en medias horas
    no: se respetan las del origen, redondeadas a centésimas).
    """
    from types import SimpleNamespace
    try:
        horas = round(float(horas), 2)
    except (TypeError, ValueError):
        raise error(422, "valor_no_valido", valor=horas)
    if not (0 < horas <= 24):
        raise error(400, "imputar_mas_de_24h", horas=horas)
    payload = SimpleNamespace(project_id=project_id, task_id=task_id, date=fecha, hours=horas,
                              description=description, is_billable=bool(is_billable),
                              force_duplicate=bool(force_duplicate))
    return validate_and_create_imputation(payload, current_user, db, antes_de_confirmar=antes_de_confirmar)


def validate_imputation_edit_allowed(imp, current_user: User, db: Session) -> None:
    """
    Validates that an existing imputation can be edited/deleted.
    Raises HTTPException on any violation.
    """

    if imp.user_id != current_user.id and current_user.role != UserRole.admin:
        raise error(403, "imputacion_ajena")

    if imp.is_approved and current_user.role != UserRole.admin:
        raise error(400, "imputacion_aprobada")

    if current_user.role != UserRole.admin:
        earliest_allowed = get_lockout_cutoff(current_user, db)
        if imp.date < earliest_allowed:
            lockout_days = (today_for_user(current_user) - earliest_allowed).days
            raise error(400, "imputacion_demasiado_antigua", dias=lockout_days)

    week_start = imp.date - timedelta(days=imp.date.weekday())
    ts = db.query(Timesheet).filter(
        Timesheet.user_id == imp.user_id,
        Timesheet.week_start == week_start,
    ).first()
    if ts and ts.status in [TimesheetStatus.submitted, TimesheetStatus.approved] and current_user.role != UserRole.admin:
        raise error(400, "imputacion_hoja_enviada")
