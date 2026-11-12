"""Tarifa y coste, sincronizacion con la hoja semanal, fecha de cierre, pertenencia al proyecto y aviso de duplicados.

Parte de `app.services.imputation_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from app.core.timeutil import today_for_user
from app.models.user import User, UserRole
from app.models.financial import Timesheet
from app.models.imputation import Imputation
from app.models.mfa import Organization
from app.models.project import ProjectMember
from app.models.project import Project
from app.models.task import Task
from app.services.notifications import notify_user
from app.services.psa_flows import sync_timesheet_from_imputations_flow
from app.core.errores import ErrorDeDominio
# ── Cost ───────────────────────────────────────────────────────────────────────
import app.services.cost_service as _cost_svc


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
        raise ErrorDeDominio(
            status_code=403,
            detail="No puedes imputar horas en un proyecto al que no estás asignado.",
        )


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
