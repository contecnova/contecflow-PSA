"""
tasks/bulk.py — Bulk task operations.

Exports:
    bulk_update_tasks
"""
from __future__ import annotations

from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException

from app.models.project import Project
from app.models.task import Task
from app.models.user import UserRole
from app.services.tasks.core import apply_status_side_effects


def bulk_update_tasks(task_ids: list, updates: dict, current_user, db: Session) -> dict:
    """
    Apply status / assignee_id / priority changes to multiple tasks.
    Returns {"updated": int, "skipped": list}.
    """
    task_id_list = list(set(task_ids))
    tasks = db.query(Task).options(joinedload(Task.assignee)).filter(Task.id.in_(task_id_list)).all()

    new_status = updates.get("status")
    new_assignee_id = updates.get("assignee_id")
    new_priority = updates.get("priority")

    updated = 0
    skipped = []

    for task in tasks:
        if current_user.role in (UserRole.employee, UserRole.subcontractor):
            skipped.append({"id": task.id, "reason": "forbidden"})
            continue
        # Permitir admin
        if current_user.role == UserRole.admin:
            pass
        # Permitir pm del proyecto
        elif current_user.role == UserRole.pm:
            project = db.query(Project).filter(Project.id == task.project_id).first()
            if not (project and project.pm_id == current_user.id):
                if task.assignee_id != current_user.id:
                    skipped.append({"id": task.id, "reason": "forbidden"})
                    continue
        # Permitir team_lead si es miembro con rol lead
        elif current_user.role == UserRole.team_lead:
            from app.models.project import ProjectMember, ProjectMemberRole
            is_lead = db.query(ProjectMember).filter(
                ProjectMember.project_id == task.project_id,
                ProjectMember.user_id == current_user.id,
                ProjectMember.role == ProjectMemberRole.lead
            ).first()
            if not is_lead:
                if task.assignee_id != current_user.id:
                    skipped.append({"id": task.id, "reason": "forbidden"})
                    continue
        # Otros solo si son asignee
        else:
            if task.assignee_id != current_user.id:
                skipped.append({"id": task.id, "reason": "forbidden"})
                continue

        if new_status and new_status != task.status:
            apply_status_side_effects(task, new_status)
            task.status = new_status

        if new_assignee_id is not None:
            task.assignee_id = new_assignee_id or None
        if new_priority is not None:
            task.priority = new_priority

        task.version = (task.version or 1) + 1
        updated += 1

    db.commit()
    return {"updated": updated, "skipped": skipped}
