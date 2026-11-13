"""
Sprint service — all database operations for sprint management.
"""
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from typing import Optional, List

from app.models.task import ESTADOS_DE_TAREA_TERMINADOS
from app.models.task import Task
from app.models.sprints import Sprint, SprintTask, SprintStatus
from app.models.project import Project
from datetime import timedelta
from app.core import timeutil


def list_all_sprints(
    db: Session,
    organization_id: Optional[str],
    is_superadmin: bool,
    status: Optional[str],
    limit: int,
    project_id: Optional[str] = None,
) -> List[Sprint]:
    q = db.query(Sprint).options(joinedload(Sprint.project))
    if project_id:   # revisión 2026-11: el filtro de sprint del tablero lo mandaba y se ignoraba
        q = q.filter(Sprint.project_id == project_id)
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
    current_user=None,
) -> List[Sprint]:
    """List sprints for a project. Audit #62: org-scoped via Project when current_user is provided."""
    q = db.query(Sprint).options(
        joinedload(Sprint.sprint_tasks).joinedload(SprintTask.task).joinedload(Task.assignee)
    ).filter(Sprint.project_id == project_id)
    if current_user is not None and not getattr(current_user, "is_superadmin", False) and getattr(current_user, "organization_id", None):
        q = q.join(Project, Sprint.project_id == Project.id).filter(
            Project.organization_id == current_user.organization_id
        )
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
    from app.core.events import emit, EventType
    emit(db, EventType.SPRINT_CREATED,
         {"sprint_id": sprint.id, "name": sprint.name, "project_id": sprint.project_id,
          "number": sprint.number},
         resource_type="sprint", resource_id=sprint.id, project_id=sprint.project_id)


def _apply_org_scope(q, current_user):
    """Audit #62: scope a Sprint query by Project.organization_id."""
    if current_user is None:
        return q
    if getattr(current_user, "is_superadmin", False):
        return q
    if not getattr(current_user, "organization_id", None):
        return q
    return q.join(Project, Sprint.project_id == Project.id).filter(
        Project.organization_id == current_user.organization_id
    )


def get_sprint_simple(
    db: Session, sprint_id: str, project_id: str, current_user=None
) -> Optional[Sprint]:
    q = db.query(Sprint).filter(
        Sprint.id == sprint_id, Sprint.project_id == project_id
    )
    q = _apply_org_scope(q, current_user)
    return q.first()


def get_sprint_with_tasks(
    db: Session, sprint_id: str, project_id: str, current_user=None
) -> Optional[Sprint]:
    q = (
        db.query(Sprint)
        .options(
            joinedload(Sprint.sprint_tasks)
            .joinedload(SprintTask.task)
            .joinedload(Task.assignee)
        )
        .filter(Sprint.id == sprint_id, Sprint.project_id == project_id)
    )
    q = _apply_org_scope(q, current_user)
    return q.first()


def get_sprint_with_tasks_by_id(db: Session, sprint_id: str, current_user=None) -> Optional[Sprint]:
    q = (
        db.query(Sprint)
        .options(
            joinedload(Sprint.sprint_tasks)
            .joinedload(SprintTask.task)
            .joinedload(Task.assignee)
        )
        .filter(Sprint.id == sprint_id)
    )
    q = _apply_org_scope(q, current_user)
    return q.first()


def get_sprint_for_charts(
    db: Session, sprint_id: str, project_id: str, current_user=None
) -> Optional[Sprint]:
    q = (
        db.query(Sprint)
        .options(joinedload(Sprint.sprint_tasks).joinedload(SprintTask.task))
        .filter(Sprint.id == sprint_id, Sprint.project_id == project_id)
    )
    q = _apply_org_scope(q, current_user)
    return q.first()


def get_active_sprint_for_project(db: Session, project_id: str, current_user=None) -> Optional[Sprint]:
    q = db.query(Sprint).filter(
        Sprint.project_id == project_id, Sprint.status == SprintStatus.active
    )
    q = _apply_org_scope(q, current_user)
    return q.first()


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
        if existing and existing.is_active == True:
            continue
        max_order = (
            db.query(func.max(SprintTask.backlog_order))
            .filter(SprintTask.sprint_id == sprint_id, SprintTask.is_active == True)
            .scalar() or 0
        )
        if existing and existing.is_active == False:
            existing.is_active = True
            existing.backlog_order = max_order + 1
            added += 1
            continue
        db.add(SprintTask(sprint_id=sprint_id, task_id=task_id, backlog_order=max_order + 1))
        added += 1
    db.commit()
    return added


def get_sprint_task(
    db: Session, sprint_id: str, task_id: str
) -> Optional[SprintTask]:
    return db.query(SprintTask).filter(
        SprintTask.sprint_id == sprint_id, SprintTask.task_id == task_id, SprintTask.is_active == True
    ).first()


def delete_sprint_task(db: Session, st: SprintTask) -> None:
    sprint_id = st.sprint_id
    st.is_active = False
    db.commit()
    from app.core.events import emit, EventType
    emit(db, EventType.SPRINT_DELETED,
         {"sprint_task_removed": True, "sprint_id": sprint_id, "task_id": st.task_id},
         resource_type="sprint_task", resource_id=sprint_id)


def reorder_sprint_backlog(
    db: Session, sprint_id: str, task_ids: List[str]
) -> None:
    for i, task_id in enumerate(task_ids):
        st = db.query(SprintTask).filter(
            SprintTask.sprint_id == sprint_id, SprintTask.task_id == task_id, SprintTask.is_active == True
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
            SprintTask.is_active == True,
        )
        .scalar_subquery()
    )
    return (
        db.query(Task)
        .options(joinedload(Task.assignee))
        .filter(
            Task.project_id == project_id,
            Task.status.notin_(ESTADOS_DE_TAREA_TERMINADOS),
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


# ── Serialization helpers ───────────────────────────────────────────────────

def serialize_task(t) -> dict:
    return {
        "id": t.id, "code": t.code, "title": t.title,
        "status": t.status, "priority": t.priority,
        "story_points": t.story_points,
        "estimated_hours": t.estimated_hours,
        "assignee_id": t.assignee_id,
        "assignee_name": t.assignee.full_name if t.assignee else None,
        "due_date": str(t.due_date) if t.due_date else None,
        "tags": t.tags,
        "blocked_reason": t.blocked_reason,
    }


def serialize_sprint(s, include_tasks: bool = False) -> dict:
    duration_days = (s.end_date - s.start_date).days if s.start_date and s.end_date else 0
    today = timeutil.today()
    days_remaining = (s.end_date - today).days if s.end_date and s.status == SprintStatus.active else None
    result = {
        "id": s.id, "number": s.number, "name": s.name,
        "goal": s.goal, "status": s.status,
        "start_date": str(s.start_date) if s.start_date else None,
        "end_date": str(s.end_date) if s.end_date else None,
        "duration_days": duration_days,
        "days_remaining": days_remaining,
        "planned_points": s.planned_points or 0,
        "completed_points": s.completed_points or 0,
        "velocity": s.velocity,
        "went_well": s.went_well,
        "to_improve": s.to_improve,
        "action_items": s.action_items,
        "created_at": str(s.created_at)[:10] if s.created_at else None,
        "task_count": len([st for st in s.sprint_tasks if st.is_active == True]),
    }
    if include_tasks:
        result["tasks"] = [serialize_task(st.task) for st in s.sprint_tasks if st.task and st.is_active == True]
    return result


def compute_sprint_burndown(sprint, db) -> list:
    """Calculate daily burndown data for a sprint."""
    if not sprint.start_date or not sprint.end_date:
        return []
    tasks = [st.task for st in sprint.sprint_tasks if st.task and st.is_active == True]
    total_points = sum(t.story_points or 0 for t in tasks)
    today = timeutil.today()
    end = min(sprint.end_date, today)
    start = sprint.start_date
    burndown = []
    current = start
    while current <= end:
        completed = sum(
            t.story_points or 0 for t in tasks
            if t.status == "done" and t.completed_at and t.completed_at.date() <= current
        )
        ideal_pct = 1 - ((current - start).days / max((sprint.end_date - start).days, 1))
        burndown.append({
            "date": str(current)[5:],
            "remaining": max(total_points - completed, 0),
            "ideal": round(total_points * ideal_pct, 1),
        })
        current += timedelta(days=1)
    return burndown
