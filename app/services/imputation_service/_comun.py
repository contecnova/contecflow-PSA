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
from app.core.codigos_de_error import error


def resolve_user_rate(db: Session, user: User, on_date: Optional[date] = None,
                      project_id: Optional[str] = None) -> float:
    """Cost per hour for `user` on `on_date`. Externos: la tarifa del proveedor
    vigente (por proyecto). Versioned UserCostProfile takes precedence,
    legacy `User.hourly_rate` is the fallback. Returns 0.0 when neither has data."""
    return _cost_svc.cost_per_hour(db, user, on_date, project_id) or 0.0


# §5 (auditoría 22-11-2026): `compute_cost` (solo reexportada, sin llamadas; el
# coste se calcula con `cost_service.cost_amount`) retirada.


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
    # Solo miembros ACTIVOS (16-11-2026): al terminar la asignacion de un
    # externo (o dar de baja a un miembro) deja de poder imputar ahi.
    is_member = db.query(ProjectMember.id).filter(
        ProjectMember.project_id == project.id,
        ProjectMember.user_id == current_user.id,
        ProjectMember.is_active.isnot(False),
    ).first() is not None
    is_task_assignee = bool(task and task.assignee_id == current_user.id)
    # Un externo solo imputa mientras es miembro (su asignacion vigente): tener
    # una tarea asignada de antes no basta.
    if current_user.role == UserRole.subcontractor:
        is_task_assignee = False
    if not (is_pm or is_member or is_task_assignee):
        raise error(403, "imputar_proyecto_no_asignado")


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

    from app.services.texto_para_usuario import texto_para
    _t = lambda clave, **p: texto_para(db, manager_id, clave, **p)  # noqa: E731
    task_label = task.title if task and task.title else _t("imputacion_forzada.sin_tarea")
    body = _t("imputacion_forzada.mensaje", nombre=current_user.full_name, proyecto=project.name,
              tarea=task_label, fecha=imputation.date, horas=imputation.hours)
    if duplicate_imputation_id:
        body += " " + _t("imputacion_forzada.ya_existia", id=duplicate_imputation_id)
    body += " " + _t("imputacion_forzada.revisa")

    notify_user(
        db,
        manager_id,
        "system",
        _t("imputacion_forzada.titulo"),
        body,
        resource="imputations",
        resource_id=imputation.id,
        action_url="/time",
    )
