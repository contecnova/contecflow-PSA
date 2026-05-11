"""
tasks/queries.py — Pure query helpers for tasks (no side-effects).

Exports:
    get_task_by_id
    get_tasks_for_project
    get_project_member_ids
    task_query_for_user
    project_for_user
    build_task_list_query
"""
from __future__ import annotations

from datetime import date as _date
from typing import Optional, TYPE_CHECKING

from sqlalchemy.orm import Session, joinedload

from app.models.project import Project
from app.models.task import Task, TaskComment, TaskStatus

if TYPE_CHECKING:
    pass


def task_query_for_user(db: Session, current_user):
    """Return a Task query scoped to the current user's organization.

    Superadmin bypass: ver project_for_user para la justificación.
    """
    q = db.query(Task).join(Project, Task.project_id == Project.id)
    is_super = bool(getattr(current_user, "is_superadmin", False))
    if not is_super and current_user.organization_id:
        q = q.filter(Project.organization_id == current_user.organization_id)
    return q


def project_for_user(db: Session, project_id: str, current_user) -> Optional[Project]:
    """Return a Project scoped to the current user's organization or None.

    Superadmin bypass: si el user es superadmin se omite el filtro de
    organización (mismo patrón que pipeline_service, approval_engine,
    ai_provider_service). Antes este query devolvía None para un superadmin
    de la org "default" intentando acceder a proyectos de otra tenancy,
    rompiendo la vista de kanban con 404 "Proyecto no encontrado".
    """
    q = db.query(Project).filter(Project.id == project_id)
    is_super = bool(getattr(current_user, "is_superadmin", False))
    if not is_super and current_user.organization_id:
        q = q.filter(Project.organization_id == current_user.organization_id)
    return q.first()


def get_task_by_id(db: Session, task_id: str) -> Optional[Task]:
    """Fetch a single task by id without org scoping."""
    return db.query(Task).filter(Task.id == task_id).first()


def get_tasks_for_project(db: Session, project_id: str) -> list:
    """Return all non-cancelled top-level tasks for a project."""
    from app.models.task import TaskStatus
    return (
        db.query(Task)
        .options(joinedload(Task.assignee))
        .filter(
            Task.project_id == project_id,
            Task.status != TaskStatus.cancelled,
            Task.parent_task_id == None,
        )
        .all()
    )


def get_project_member_ids(db: Session, project_id: str) -> list:
    """Return user_ids of all project members."""
    from app.models.project import ProjectMember
    members = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id
    ).all()
    return [m.user_id for m in members if getattr(m, "user_id", None)]


def build_task_list_query(
    db: Session,
    current_user,
    *,
    assigned_to_me: bool = False,
    assignee_id: Optional[str] = None,
    project_id: Optional[str] = None,
    phase_id: Optional[str] = None,
    status: Optional[str] = None,
    priority=None,
    search: Optional[str] = None,
    overdue_only: bool = False,
    sprint_id: Optional[str] = None,
    parent_task_id: Optional[str] = None,
):
    """Build a filtered Task query scoped to the current user's org.

    Centralises all list-endpoint filter logic so the endpoint only handles
    HTTP concerns (pagination, response headers).
    """
    from app.models.user import UserRole

    q = task_query_for_user(db, current_user).options(
        joinedload(Task.assignee),
        joinedload(Task.reporter),
    )

    if assigned_to_me or getattr(current_user, "role", None) in (
        UserRole.employee, UserRole.subcontractor
    ):
        q = q.filter(Task.assignee_id == current_user.id)
    elif assignee_id:
        q = q.filter(Task.assignee_id == assignee_id)

    if project_id:
        q = q.filter(Task.project_id == project_id)
    if phase_id:
        q = q.filter(Task.phase_id == phase_id)
    if sprint_id:
        q = q.filter(Task.sprint_id == sprint_id)
    if parent_task_id:
        q = q.filter(Task.parent_task_id == parent_task_id)

    if status:
        status_vals = [s.strip() for s in status.split(",") if s.strip()]
        if len(status_vals) == 1:
            q = q.filter(Task.status == status_vals[0])
        elif status_vals:
            q = q.filter(Task.status.in_(status_vals))

    if priority:
        q = q.filter(Task.priority == priority)

    if search:
        q = q.filter(
            (Task.title.ilike(f"%{search}%")) |
            (Task.code.ilike(f"%{search}%"))
        )

    if overdue_only:
        q = q.filter(
            Task.due_date < _date.today(),
            Task.status.not_in([TaskStatus.done, TaskStatus.cancelled]),
        )

    return q
