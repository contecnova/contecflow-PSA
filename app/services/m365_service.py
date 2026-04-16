"""
Service helpers for Microsoft 365 integration endpoints.
Encapsulates database queries used by the m365 router.
"""
from datetime import date
from typing import List

from sqlalchemy.orm import Session


def get_upcoming_milestones(db: Session, cutoff: date, limit: int = 50) -> list:
    """Return milestones with due_date up to cutoff."""
    from app.models.financial import ProjectMilestone
    return (
        db.query(ProjectMilestone)
        .filter(ProjectMilestone.due_date <= cutoff)
        .limit(limit)
        .all()
    )


def get_active_tasks_for_project(db: Session, project_id: str, limit: int = 200) -> list:
    """Return non-terminal tasks for a project."""
    from app.models.task import Task
    return (
        db.query(Task)
        .filter(
            Task.project_id == project_id,
            Task.status.notin_(["done", "cancelled", "closed"]),
        )
        .limit(limit)
        .all()
    )
