"""
tasks/queries.py — Pure query helpers for tasks (no side-effects).

Exports:
    get_task_by_id
    get_tasks_for_project
    get_project_member_ids
    task_query_for_user
    project_for_user
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from sqlalchemy.orm import Session, joinedload

from app.models.project import Project
from app.models.task import Task, TaskComment

if TYPE_CHECKING:
    pass


def task_query_for_user(db: Session, current_user):
    """Return a Task query scoped to the current user's organization."""
    q = db.query(Task).join(Project, Task.project_id == Project.id)
    if current_user.organization_id:
        q = q.filter(Project.organization_id == current_user.organization_id)
    return q


def project_for_user(db: Session, project_id: str, current_user) -> Optional[Project]:
    """Return a Project scoped to the current user's organization or None."""
    q = db.query(Project).filter(Project.id == project_id)
    if current_user.organization_id:
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
