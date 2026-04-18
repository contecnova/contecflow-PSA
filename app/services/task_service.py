"""
task_service.py — Lógica de negocio para tareas.

Funciones exportadas:
  TASK_VALID_TRANSITIONS
  validate_task_transition(current_status, new_status) -> raises HTTPException if invalid
  apply_status_side_effects(task, new_status)
  cascade_reschedule(task_id, new_end_date, db) -> dict
  bulk_update_tasks(task_ids, updates, current_user, db) -> dict
"""
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone, timedelta, date
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import BackgroundTasks

from sqlalchemy.orm import Session

from app.models.task import TaskStatus
from app.db.session import SessionLocal
from app.models.bookings import TaskDependency, DependencyType
from app.models.project import Project
from app.models.task import Task, TaskStatus, TaskComment
from app.models.task import Task as TaskModel
from app.models.user import UserRole
from app.schemas import TaskOut as TaskOutSchema
from app.services.numbering import next_numbered_code
from app.services.semantic_classifier import SemanticAssigner
from datetime import date as _date
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload


# ── Transition table ───────────────────────────────────────────────────────────

TASK_VALID_TRANSITIONS: dict = {
    status: {s for s in TaskStatus if s != status} for status in TaskStatus
}


def validate_task_transition(current_status: TaskStatus, new_status: TaskStatus) -> None:
    """Raises HTTPException(400) if the transition is not allowed."""
    allowed = TASK_VALID_TRANSITIONS.get(current_status, set())
    if new_status not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Transición de estado no permitida: '{current_status.value}' → '{new_status.value}'",
        )


def apply_status_side_effects(task, new_status: TaskStatus) -> None:
    """Set started_at / completed_at timestamps when status changes."""
    if new_status == TaskStatus.in_progress:
        task.started_at = datetime.now(timezone.utc)
    elif new_status == TaskStatus.done:
        task.completed_at = datetime.now(timezone.utc)

        # Trigger OKR sync si la tarea está vinculada a un proyecto con OKRs
        try:
            from app.services import okr_service
            db = getattr(task, '_sa_instance_state', None)
            if hasattr(task, 'project_id') and task.project_id:
                session = getattr(task, '_sa_instance_state', None)
                if session:
                    db_session = session.session
                    krs = db_session.query(okr_service.KeyResult).join(okr_service.Objective).filter(
                        okr_service.Objective.project_id == task.project_id
                    ).all()
                    for kr in krs:
                        try:
                            okr_service.sync_kr_from_tasks(kr.id, task.assignee_id or "system", db_session)
                        except Exception as e:
                            import logging
                            logging.getLogger(__name__).warning(f"OKR sync failed for KR {kr.id}: {e}")
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"OKR sync global error: {e}")


# ── Cascade reschedule (BFS) ───────────────────────────────────────────────────

def cascade_reschedule(task_id: str, new_end_date: date, db: Session) -> dict:
    """
    Propagate a due-date shift to all FS successor tasks via BFS.
    Returns rescheduled task list + total count.
    """

    root_task = db.query(Task).filter(Task.id == task_id).first()
    if not root_task:
        raise HTTPException(404, "Tarea no encontrada")

    old_end = root_task.due_date
    if not old_end:
        raise HTTPException(400, "La tarea raíz no tiene fecha de fin definida")

    delta = new_end_date - old_end
    if delta.days == 0:
        return {
            "rescheduled": [],
            "total_shifted": 0,
            "message": "No hay cambio de fecha — nada que replanificar",
        }

    root_task.due_date = new_end_date
    if root_task.start_date:
        root_task.start_date = root_task.start_date + delta
    rescheduled = [{
        "task_id": root_task.id,
        "title": root_task.title,
        "old_due_date": str(old_end),
        "new_due_date": str(new_end_date),
        "shift_days": delta.days,
    }]

    visited = {task_id}
    queue: deque = deque([task_id])

    while queue:
        current_id = queue.popleft()
        current_task = db.query(Task).filter(Task.id == current_id).first()
        if not current_task or not current_task.due_date:
            continue

        deps = db.query(TaskDependency).filter(
            TaskDependency.predecessor_id == current_id,
            TaskDependency.dependency_type == DependencyType.finish_to_start,
        ).all()

        for dep in deps:
            succ_id = dep.successor_id
            if succ_id in visited:
                continue
            visited.add(succ_id)
            succ = db.query(Task).filter(Task.id == succ_id).first()
            if not succ:
                continue

            lag = timedelta(days=dep.lag_days or 0)
            new_start = current_task.due_date + timedelta(days=1) + lag
            if succ.start_date and succ.due_date:
                duration = succ.due_date - succ.start_date
                old_due = succ.due_date
                succ.start_date = new_start
                succ.due_date = new_start + duration
            elif succ.due_date:
                old_due = succ.due_date
                shift_here = new_start - (succ.start_date or succ.due_date)
                succ.due_date = succ.due_date + shift_here
            else:
                continue

            rescheduled.append({
                "task_id": succ.id,
                "title": succ.title,
                "old_due_date": str(old_due),
                "new_due_date": str(succ.due_date),
                "shift_days": (succ.due_date - old_due).days,
            })
            queue.append(succ_id)

    db.commit()
    return {"rescheduled": rescheduled, "total_shifted": len(rescheduled)}


# ── Bulk update ────────────────────────────────────────────────────────────────

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
            allowed = TASK_VALID_TRANSITIONS.get(task.status, set())
            if new_status not in allowed:
                skipped.append({
                    "id": task.id,
                    "reason": f"invalid_transition:{task.status.value}->{new_status.value}",
                })
                continue
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


# ── Query helpers (scoped to org) ──────────────────────────────────────────────

def task_query_for_user(db: Session, current_user):
    q = db.query(Task).join(Project, Task.project_id == Project.id)
    if current_user.organization_id:
        q = q.filter(Project.organization_id == current_user.organization_id)
    return q


def project_for_user(db: Session, project_id: str, current_user) -> Optional["Project"]:
    q = db.query(Project).filter(Project.id == project_id)
    if current_user.organization_id:
        q = q.filter(Project.organization_id == current_user.organization_id)
    return q.first()


# ── Kanban ─────────────────────────────────────────────────────────────────────

def get_kanban_payload(db: Session, project_id: str, current_user) -> dict:

    project = project_for_user(db, project_id, current_user)
    if not project:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")

    if current_user.role in (UserRole.employee, UserRole.subcontractor):
        has_task = db.query(Task).filter(
            Task.project_id == project_id,
            Task.assignee_id == current_user.id,
        ).first()
        if not has_task:
            raise HTTPException(status_code=403, detail="No tienes tareas en este proyecto")

    tasks = db.query(Task).options(
        joinedload(Task.assignee)
    ).filter(
        Task.project_id == project_id,
        Task.status != TaskStatus.cancelled,
        Task.parent_task_id == None,
    ).all()

    columns = {s.value: [] for s in TaskStatus if s != TaskStatus.cancelled}
    for task in tasks:
        col = task.status.value
        if col in columns:
            columns[col].append(TaskOutSchema.model_validate(task))
    return columns


# ── Create ─────────────────────────────────────────────────────────────────────

def create_task_record(db: Session, payload, current_user):

    if current_user.role in (UserRole.employee, UserRole.subcontractor):
        raise HTTPException(status_code=403, detail="No tienes permiso para crear tareas")

    project = project_for_user(db, payload.project_id, current_user)
    if not project:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")

    task = Task(
        **payload.model_dump(),
        code=next_numbered_code(db, "task", prefix="TSK", padding=5),
        reporter_id=current_user.id,
        created_by=current_user.id,
    )
    try:
        db.add(task)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Código de tarea duplicado. Inténtalo de nuevo.")
    db.refresh(task)
    from app.core.events import emit, EventType
    emit(db, EventType.TASK_CREATED,
         {"title": task.title, "status": str(task.status), "assignee_id": task.assignee_id,
          "project_id": task.project_id, "code": task.code},
         actor=current_user, resource_type="task", resource_id=task.id,
         project_id=task.project_id)
    return task


# ── Get single ─────────────────────────────────────────────────────────────────

def get_task_record(db: Session, task_id: str, current_user):

    task = task_query_for_user(db, current_user).options(
        joinedload(Task.assignee),
        joinedload(Task.reporter),
        joinedload(Task.comments).joinedload(TaskComment.author),
        joinedload(Task.subtasks),
    ).filter(Task.id == task_id).first()

    if not task:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")

    if current_user.role != UserRole.admin:
        project = db.query(Project).filter(Project.id == task.project_id).first()
        is_project_pm = project and project.pm_id == current_user.id
        is_task_participant = (task.assignee_id == current_user.id or task.reporter_id == current_user.id)
        if not is_project_pm and not is_task_participant:
            raise HTTPException(status_code=403, detail="No tienes acceso a esta tarea")

    return task


# ── Update ─────────────────────────────────────────────────────────────────────

def update_task_record(db: Session, task_id: str, payload, current_user):
    import logging

    logger = logging.getLogger(__name__)

    task = task_query_for_user(db, current_user).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")

    project = project_for_user(db, task.project_id, current_user)
    if not project:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")

    if current_user.role != UserRole.admin:
        is_project_pm = project and project.pm_id == current_user.id
        if not is_project_pm and task.assignee_id != current_user.id:
            raise HTTPException(status_code=403, detail="No tienes permiso para editar esta tarea")

    old_assignee_id = task.assignee_id

    if payload.status and payload.status != task.status:
        validate_task_transition(task.status, payload.status)
        apply_status_side_effects(task, payload.status)

    for field, value in payload.model_dump(exclude_unset=True).items():
        if field == "version":
            continue
        setattr(task, field, value)

    client_version = payload.model_dump(exclude_unset=True).get("version")
    if client_version is not None and client_version != (task.version or 1):
        raise HTTPException(
            status_code=409,
            detail=f"Conflicto de edición: la tarea fue modificada por otro usuario (versión {task.version}). Recarga y reintenta.",
        )
    task.version = (task.version or 1) + 1

    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Integrity error updating task {task_id}: {str(e)}")
        raise HTTPException(status_code=409, detail="Task state conflict. Please reload and try again.")
    except Exception as e:
        db.rollback()
        logger.error(f"Database error updating task {task_id}: {str(e)}")
        raise HTTPException(status_code=503, detail="Database operation failed")

    db.refresh(task)
    from app.core.events import emit, EventType
    changed_fields = payload.model_dump(exclude_unset=True)
    new_assignee = changed_fields.get("assignee_id")
    new_status = changed_fields.get("status")
    if new_status and str(new_status) in ("done", "completed", "closed"):
        etype = EventType.TASK_COMPLETED
    elif new_assignee and new_assignee != old_assignee_id:
        etype = EventType.TASK_ASSIGNED
    else:
        etype = EventType.TASK_UPDATED
    emit(db, etype,
         {"title": task.title, "status": str(task.status), "assignee_id": task.assignee_id,
          "project_id": task.project_id, **changed_fields},
         actor=current_user, resource_type="task", resource_id=task.id,
         project_id=task.project_id)
    return task, old_assignee_id


# ── Cancel ─────────────────────────────────────────────────────────────────────

def cancel_task_record(db: Session, task_id: str) -> dict:
    import logging

    logger = logging.getLogger(__name__)

    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    task.status = TaskStatus.cancelled
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Integrity error cancelling task {task_id}: {str(e)}")
        raise HTTPException(status_code=409, detail="Cannot cancel task. State conflict.")
    except Exception as e:
        db.rollback()
        logger.error(f"Database error cancelling task {task_id}: {str(e)}")
        raise HTTPException(status_code=503, detail="Database operation failed")
    from app.core.events import emit, EventType
    emit(db, EventType.TASK_DELETED,
         {"title": task.title, "project_id": task.project_id, "reason": "cancelled"},
         resource_type="task", resource_id=task_id, project_id=task.project_id)
    return {"message": "Tarea cancelada"}


# ── Comment ────────────────────────────────────────────────────────────────────

def add_comment_record(db: Session, task_id: str, payload, current_user):
    import logging

    logger = logging.getLogger(__name__)

    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")

    if current_user.role != UserRole.admin:
        project = db.query(Project).filter(Project.id == task.project_id).first()
        is_project_pm = project and project.pm_id == current_user.id
        is_task_participant = (task.assignee_id == current_user.id or task.reporter_id == current_user.id)
        if not is_project_pm and not is_task_participant:
            raise HTTPException(status_code=403, detail="No tienes acceso a esta tarea")

    comment = TaskComment(
        task_id=task_id,
        author_id=current_user.id,
        content=payload.content,
    )
    db.add(comment)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Integrity error adding comment to task {task_id}: {str(e)}")
        raise HTTPException(status_code=409, detail="Cannot add comment. Conflict.")
    except Exception as e:
        db.rollback()
        logger.error(f"Database error adding comment to task {task_id}: {str(e)}")
        raise HTTPException(status_code=503, detail="Database operation failed")
    db.refresh(comment)
    return comment


# ── Bulk dates ─────────────────────────────────────────────────────────────────

def bulk_update_dates_record(db: Session, updates: list) -> dict:
    import logging

    logger = logging.getLogger(__name__)

    def _to_date(v):
        if not v:
            return None
        if isinstance(v, _date):
            return v
        try:
            return _date.fromisoformat(str(v)[:10])
        except (ValueError, TypeError):
            return None

    updated = 0
    errors = []
    for u in updates:
        task = db.query(TaskModel).filter(TaskModel.id == u.get("id")).first()
        if not task:
            errors.append(u.get("id"))
            continue
        if "start_date" in u:
            task.start_date = _to_date(u["start_date"])
        if "due_date" in u:
            task.due_date = _to_date(u["due_date"])
        updated += 1
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Integrity error in bulk_update_dates: {str(e)}")
        raise HTTPException(status_code=409, detail="Constraint violation in bulk date update.")
    except Exception as e:
        db.rollback()
        logger.error(f"Database error in bulk_update_dates: {str(e)}")
        raise HTTPException(status_code=503, detail="Database operation failed")
    return {"updated": updated, "errors": errors}


# ── Background task helpers ────────────────────────────────────────────────────

def record_reassign_feedback_bg(background_tasks, db, item_id: str, item_type: str):
    """Record reassignment as implicit negative feedback for the previous assignee."""

    def _run():
        _db = SessionLocal()
        try:
            from app.models.semantic_engine import SemAssignment
            assignment = _db.query(SemAssignment).filter(
                SemAssignment.item_id == item_id,
                SemAssignment.item_type == item_type,
            ).order_by(SemAssignment.created_at.desc()).first()
            if assignment and assignment.was_accepted is None:
                assignment.was_accepted = False
                _db.commit()
        except Exception:
            pass
        finally:
            _db.close()

    background_tasks.add_task(_run)


def refresh_profile_bg(background_tasks: "BackgroundTasks", db: "Session", user_id: str) -> None:
    """Schedule a semantic profile refresh as a background task."""

    def _run():
        _db = SessionLocal()
        try:
            SemanticAssigner(_db).refresh_user_profile(user_id)
        except Exception:
            pass
        finally:
            _db.close()

    background_tasks.add_task(_run)
