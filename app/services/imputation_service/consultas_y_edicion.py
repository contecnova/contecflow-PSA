"""Consulta, edicion y borrado de imputaciones; resumen semanal, alertas y estado de cierre.

Parte de `app.services.imputation_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional
from sqlalchemy.orm import Session, joinedload
from app.core.config import settings
from app.models.user import User, UserRole
from app.models.imputation import Imputation
from app.models.imputation import ImputationAlert
from app.models.user import User as UserModel
from app.schemas import WeekSummary
from app.schemas.time_tracking import LockoutStatusOut
from app.schemas.time_tracking import ImputationAlertOut
from app.core.errores import ErrorDeDominio
from app.core import timeutil

from app.services.imputation_service._comun import (
    get_lockout_cutoff,
    sync_imputation_week_timesheet,
)


def update_imputation_fields(imp, payload, db: Session, current_user: User = None):
    """Apply field updates from payload and recompute cost if hours changed. Commits. Valida límites diarios y semanales."""
    from app.models.user import User as UserModel
    from app.models.imputation import Imputation
    from sqlalchemy import func, and_
    from datetime import timedelta

    # Obtener usuario actual de la imputación
    user = db.query(UserModel).filter(UserModel.id == imp.user_id).first()
    if not user:
        raise ErrorDeDominio(status_code=404, detail="Usuario no encontrado para la imputación")

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
            raise ErrorDeDominio(status_code=403, detail="No tienes permiso para editar campos críticos de la imputación")
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
        raise ErrorDeDominio(
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
        raise ErrorDeDominio(
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
        raise ErrorDeDominio(status_code=404, detail="Alert not found")
    if alert.user_id != current_user.id:
        raise ErrorDeDominio(status_code=403, detail="Cannot dismiss another user's alert")
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
