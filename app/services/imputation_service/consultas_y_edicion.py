"""Consulta, edicion y borrado de imputaciones; resumen semanal, alertas y estado de cierre.

Parte de `app.services.imputation_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional
from sqlalchemy.orm import Session, joinedload, selectinload
from app.services.settings_service.por_empresa import capacidad_semanal
from app.models.user import User, UserRole
from app.models.imputation import Imputation
from app.models.task import Task, TaskComment
from app.models.imputation import ImputationAlert
from app.models.user import User as UserModel
from app.schemas import WeekSummary
from app.schemas.time_tracking import LockoutStatusOut
from app.schemas.time_tracking import ImputationAlertOut
from app.core.errores import ErrorDeDominio
from app.core import timeutil
from app.core.paginacion import Pagina, Paginacion, paginar

from app.services.imputation_service._comun import (
    get_lockout_cutoff,
    sync_imputation_week_timesheet,
)
from app.core.codigos_de_error import error
from app.core.timeutil import today_for_user
from app.models.project import Project


def update_imputation_fields(imp, payload, db: Session, current_user: User = None):
    """Apply field updates from payload and recompute cost if hours changed. Commits. Valida límites diarios y semanales."""
    from app.models.user import User as UserModel
    from app.models.imputation import Imputation
    from sqlalchemy import func, and_
    from datetime import timedelta

    # Obtener usuario actual de la imputación
    user = db.query(UserModel).filter(UserModel.id == imp.user_id).first()
    if not user:
        raise error(404, "no_encontrado", detail="Usuario no encontrado para la imputación", que="usuario")

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
        # Auditoría 22-11-2026 (M32): `description` e `is_billable` (los que la
        # persona pone al imputar) se ignoraban en silencio al editar.
        allowed_fields = {"hours", "notes", "body", "description", "is_billable"}
        filtered_payload = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if k in allowed_fields}
        if set(payload.model_dump(exclude_unset=True).keys()) & critical_fields:
            raise error(403, "sin_permiso", detail="No tienes permiso para editar campos críticos de la imputación")
    else:
        filtered_payload = payload.model_dump(exclude_unset=True)

    # Si se va a cambiar horas, validar límites
    new_hours = filtered_payload.get("hours", payload.hours if payload.hours is not None else imp.hours)
    imputation_date = imp.date
    # Límite diario: sumar todas las imputaciones del usuario ese día, excepto la actual
    existing_hours = db.query(func.sum(Imputation.hours)).filter(
        Imputation.user_id == user.id,
        Imputation.date == imputation_date,
        Imputation.id != imp.id,
        Imputation.is_active.is_(True),   # A45: sin contar las borradas
    ).scalar() or 0.0
    if existing_hours + new_hours > 24:
        raise error(400, "imputar_mas_de_24h", detail=f"No puedes imputar más de 24h en un día. Ya tienes {existing_hours}h registradas para el {imputation_date}.", horas=existing_hours)

    # Límite semanal: sumar todas las imputaciones del usuario esa semana, excepto la actual
    week_start = imputation_date - timedelta(days=imputation_date.weekday())
    week_end = week_start + timedelta(days=6)
    weekly_hours = db.query(func.sum(Imputation.hours)).filter(
        and_(
            Imputation.user_id == user.id,
            Imputation.date >= week_start,
            Imputation.date <= week_end,
            Imputation.id != imp.id,
            Imputation.is_active.is_(True),
        )
    ).scalar() or 0.0
    weekly_capacity = capacidad_semanal(db, user)
    # Horas extra (18-11-2026): el mismo control que al imputar (horas_extra/control.py).
    from app.services.horas_extra import control as control_horas_extra
    weekly_capacity += control_horas_extra.capacidad_semanal_extra(db, user.id, imputation_date)
    if weekly_hours + new_hours > weekly_capacity:
        raise error(400, "imputar_supera_capacidad", detail=f"Excederías la capacidad semanal ({weekly_capacity}h). Semana actual: {weekly_hours}h, nueva imputación: {new_hours}h.", capacidad=weekly_capacity, semana=weekly_hours, nueva=new_hours)

    control_horas_extra.antes_de_imputar(db, user.id, imputation_date, new_hours, excluir_imputacion=imp.id)

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
    control_horas_extra.despues_de_imputar(db, imp.user_id, imp.date, getattr(current_user, "id", None))
    return imp


def _alcance_por_rol(db: Session, current_user: User, q):
    from sqlalchemy import or_
    rol = getattr(current_user.role, "value", current_user.role)
    if getattr(current_user, "is_superadmin", False) or rol not in ("pm", "team_lead"):
        return q
    condiciones = [Imputation.user_id == current_user.id]
    if rol == "pm":
        condiciones.append(Imputation.project_id.in_(
            db.query(Project.id).filter(Project.pm_id == current_user.id)))
    else:
        from app.services.horas_extra.consultas import subordinados
        equipo = subordinados(db, current_user)
        if equipo:
            condiciones.append(Imputation.user_id.in_(list(equipo)))
    return q.filter(or_(*condiciones))


def lockout_status_payload(current_user: User, db: Session):
    """Return LockoutStatusOut for the current user."""
    # M32 (auditoría 22-11-2026): «hoy» de la persona y los rangos rellenos
    # (antes siempre vacíos): bloqueado hasta el día anterior al corte; editable
    # del corte a hoy. El administrador no tiene bloqueo.
    lockout_cutoff = get_lockout_cutoff(current_user, db)
    today = today_for_user(current_user)
    lockout_days = (today - lockout_cutoff).days
    es_admin = current_user.role == UserRole.admin
    return LockoutStatusOut(
        lockout_days=lockout_days,
        current_date=today,
        lockout_cutoff_date=lockout_cutoff,
        locked_date_ranges=[] if es_admin else [{"from": None, "to": str(lockout_cutoff - timedelta(days=1))}],
        editable_date_ranges=[{"from": None if es_admin else str(lockout_cutoff), "to": str(today)}],
    )


def list_alerts_payload(db: Session, current_user: User, acknowledged: bool,
                        pagina: Optional[Paginacion] = None) -> Pagina:
    """Return ImputationAlertOut list for the current user."""
    q = db.query(ImputationAlert).filter(ImputationAlert.user_id == current_user.id)
    if not acknowledged:
        q = q.filter(ImputationAlert.dismissed_at == None)
    return paginar(q.order_by(ImputationAlert.alert_date.desc(), ImputationAlert.id),
                   pagina, "imputations.alerts").mapear(lambda a: ImputationAlertOut(
            id=a.id,
            user_id=a.user_id,
            alert_date=a.alert_date,
            alert_type=a.alert_type,
            created_at=a.created_at,
            dismissed_at=a.dismissed_at,
        ))


def dismiss_alert_record(db: Session, alert_id: str, current_user: User) -> dict:
    """Dismiss an imputation alert. Raises 404/403 on violations."""
    alert = db.query(ImputationAlert).filter(ImputationAlert.id == alert_id).first()
    if not alert:
        raise error(404, "no_encontrado", detail="Alert not found", que="alerta")
    if alert.user_id != current_user.id:
        raise error(403, "alerta_ajena", detail="Cannot dismiss another user's alert")
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
    capacity = capacidad_semanal(db, current_user)
    # M32: con capacidad 0 (persona sin jornada) ya no hay ZeroDivisionError.
    load_pct = round((total_hours / capacity) * 100, 1) if capacity else 0.0

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
    solo_temporizador: bool = False,
):

    # Segunda auditoria 2026-11 (N+1): `ImputationOut.task` es un `TaskOut`
    # completo —responsable, autor y comentarios con su autor—; sin cargarlos
    # aqui, cada fila hacia su propia consulta de comentarios. `TaskOut.real_hours`
    # suma `Task.imputations`: su `lazy="selectin"` no se aplica al llegar a la
    # tarea desde una imputacion (SQLAlchemy corta el ciclo y cae a carga
    # perezosa, una consulta por fila), asi que se pide de forma explicita.
    q = db.query(Imputation).options(
        joinedload(Imputation.user),
        joinedload(Imputation.task).selectinload(Task.imputations),
        joinedload(Imputation.task).joinedload(Task.assignee),
        joinedload(Imputation.task).joinedload(Task.reporter),
        joinedload(Imputation.task).selectinload(Task.comments).joinedload(TaskComment.author),
        joinedload(Imputation.project),
    ).filter(Imputation.is_active == True)

    # Scope: employees and subcontractors only see their own imputations
    if current_user.role in (UserRole.employee, UserRole.subcontractor):
        q = q.filter(Imputation.user_id == current_user.id)
    elif user_id:
        q = q.filter(Imputation.user_id == user_id)
    # M33 (auditoría 22-11-2026), estándar PSA: el PM ve las imputaciones de los
    # proyectos que dirige; el team lead, las de su equipo (cadena de mando);
    # los dos, también las suyas. RR. HH. y administración, las de la empresa.
    q = _alcance_por_rol(db, current_user, q)

    if project_id:
        q = q.filter(Imputation.project_id == project_id)
    if task_id:
        q = q.filter(Imputation.task_id == task_id)
    if date_from:
        q = q.filter(Imputation.date >= date_from)
    if date_to:
        q = q.filter(Imputation.date <= date_to)
    # Auditoria 04b (B4), 23-11-2026: historial del temporizador filtrado aqui y
    # no en el cliente sobre la primera pagina (salia corto con imputaciones a mano).
    if solo_temporizador:
        q = q.filter(Imputation.timer_session_id.isnot(None))

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
    # Horas extra (18-11-2026): si el exceso del día desaparece, su declaración pendiente se anula.
    from app.services.horas_extra import control as control_horas_extra
    control_horas_extra.despues_de_imputar(db, user_id, work_date, None)
