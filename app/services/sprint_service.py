"""
Sprint service — all database operations for sprint management.
"""
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from typing import Optional, List

from app.models.task import Task
from app.models.sprints import Sprint, SprintTask, SprintStatus
from app.models.project import Project


def list_all_sprints(
    db: Session,
    organization_id: Optional[str],
    is_superadmin: bool,
    status: Optional[str],
    limit: int,
) -> List[Sprint]:
    q = db.query(Sprint).options(joinedload(Sprint.project))
    if not is_superadmin and organization_id:
        org_project_ids = db.query(Project.id).filter(
            Project.organization_id == organization_id
        ).scalar_subquery()
        q = q.filter(Sprint.project_id.in_(org_project_ids))
    if status:
        q = q.filter(Sprint.status == status)
    return q.order_by(Sprint.start_date.desc()).limit(limit).all()


def list_sprints_for_project(
    db: Session,
    project_id: str,
    status: Optional[str],
) -> List[Sprint]:
    q = db.query(Sprint).options(
        joinedload(Sprint.sprint_tasks).joinedload(SprintTask.task).joinedload(Task.assignee)
    ).filter(Sprint.project_id == project_id)
    if status:
        q = q.filter(Sprint.status == status)
    return q.order_by(Sprint.number.desc()).all()


def get_next_sprint_number(db: Session, project_id: str) -> int:
    return (
        db.query(func.max(Sprint.number)).filter(Sprint.project_id == project_id).scalar() or 0
    ) + 1


def create_sprint(db: Session, sprint: Sprint) -> None:
    db.add(sprint)
    db.commit()


def get_sprint_simple(
    db: Session, sprint_id: str, project_id: str
) -> Optional[Sprint]:
    return db.query(Sprint).filter(
        Sprint.id == sprint_id, Sprint.project_id == project_id
    ).first()


def get_sprint_with_tasks(
    db: Session, sprint_id: str, project_id: str
) -> Optional[Sprint]:
    return (
        db.query(Sprint)
        .options(
            joinedload(Sprint.sprint_tasks)
            .joinedload(SprintTask.task)
            .joinedload(Task.assignee)
        )
        .filter(Sprint.id == sprint_id, Sprint.project_id == project_id)
        .first()
    )


def get_sprint_with_tasks_by_id(db: Session, sprint_id: str) -> Optional[Sprint]:
    return (
        db.query(Sprint)
        .options(
            joinedload(Sprint.sprint_tasks)
            .joinedload(SprintTask.task)
            .joinedload(Task.assignee)
        )
        .filter(Sprint.id == sprint_id)
        .first()
    )


def get_sprint_for_charts(
    db: Session, sprint_id: str, project_id: str
) -> Optional[Sprint]:
    return (
        db.query(Sprint)
        .options(joinedload(Sprint.sprint_tasks).joinedload(SprintTask.task))
        .filter(Sprint.id == sprint_id, Sprint.project_id == project_id)
        .first()
    )


def get_active_sprint_for_project(db: Session, project_id: str) -> Optional[Sprint]:
    return db.query(Sprint).filter(
        Sprint.project_id == project_id, Sprint.status == SprintStatus.active
    ).first()


def commit_db(db: Session) -> None:
    db.commit()


def add_tasks_to_sprint(
    db: Session,
    sprint_id: str,
    project_id: str,
    task_ids: List[str],
) -> int:
    added = 0
    for task_id in task_ids:
        task = db.query(Task).filter(
            Task.id == task_id, Task.project_id == project_id
        ).first()
        if not task:
            continue
        existing = db.query(SprintTask).filter(
            SprintTask.sprint_id == sprint_id, SprintTask.task_id == task_id
        ).first()
        if existing:
            continue
        max_order = (
            db.query(func.max(SprintTask.backlog_order))
            .filter(SprintTask.sprint_id == sprint_id)
            .scalar() or 0
        )
        db.add(SprintTask(sprint_id=sprint_id, task_id=task_id, backlog_order=max_order + 1))
        added += 1
    db.commit()
    return added


def get_sprint_task(
    db: Session, sprint_id: str, task_id: str
) -> Optional[SprintTask]:
    return db.query(SprintTask).filter(
        SprintTask.sprint_id == sprint_id, SprintTask.task_id == task_id
    ).first()


def delete_sprint_task(db: Session, st: SprintTask) -> None:
    db.delete(st)
    db.commit()


def reorder_sprint_backlog(
    db: Session, sprint_id: str, task_ids: List[str]
) -> None:
    for i, task_id in enumerate(task_ids):
        st = db.query(SprintTask).filter(
            SprintTask.sprint_id == sprint_id, SprintTask.task_id == task_id
        ).first()
        if st:
            st.backlog_order = i
    db.commit()


def get_project_backlog_tasks(db: Session, project_id: str) -> List[Task]:
    sprint_task_ids = (
        db.query(SprintTask.task_id)
        .join(Sprint)
        .filter(
            Sprint.project_id == project_id,
            Sprint.status.in_([SprintStatus.planning, SprintStatus.active]),
        )
        .scalar_subquery()
    )
    return (
        db.query(Task)
        .options(joinedload(Task.assignee))
        .filter(
            Task.project_id == project_id,
            Task.status.notin_(["done", "cancelled"]),
            Task.id.notin_(sprint_task_ids),
        )
        .order_by(Task.priority.desc(), Task.created_at)
        .all()
    )


def get_velocity_sprints(db: Session, project_id: str) -> List[Sprint]:
    return (
        db.query(Sprint)
        .filter(
            Sprint.project_id == project_id,
            Sprint.status == SprintStatus.completed,
        )
        .order_by(Sprint.number)
        .all()
    )
