from fastapi import APIRouter, Depends, HTTPException, Query, Body, BackgroundTasks, Response
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from typing import Optional, List
from datetime import datetime, timezone, date
import re
import logging

logger = logging.getLogger(__name__)

from app.db.session import get_db
from app.core.abac_enforce import enforce_abac
from app.core.deps import get_current_user, require_admin_or_pm
from app.models.user import User, UserRole
from app.models.task import Task, TaskStatus, TaskPriority, TaskComment
from app.models.project import Project
from app.services.numbering import next_numbered_code
from app.schemas.tasks import (
    TaskCreate, TaskUpdate, TaskOut, TaskCommentCreate, TaskCommentOut, BulkTaskUpdatePayload
)

router = APIRouter()


def _task_query_for_user(db: Session, current_user: User):
    q = db.query(Task).join(Project, Task.project_id == Project.id)
    if current_user.organization_id:
        q = q.filter(Project.organization_id == current_user.organization_id)
    return q


def _project_for_user(db: Session, project_id: str, current_user: User) -> Optional[Project]:
    q = db.query(Project).filter(Project.id == project_id)
    if current_user.organization_id:
        q = q.filter(Project.organization_id == current_user.organization_id)
    return q.first()

# Allowed task status transitions: key = current status, value = set of allowed next statuses
_TASK_VALID_TRANSITIONS: dict = {
    TaskStatus.backlog:     {TaskStatus.todo, TaskStatus.cancelled},
    TaskStatus.todo:        {TaskStatus.in_progress, TaskStatus.backlog, TaskStatus.cancelled, TaskStatus.done},
    TaskStatus.in_progress: {TaskStatus.in_review, TaskStatus.review, TaskStatus.blocked, TaskStatus.done, TaskStatus.todo},
    TaskStatus.blocked:     {TaskStatus.in_progress, TaskStatus.todo, TaskStatus.cancelled},
    TaskStatus.in_review:   {TaskStatus.done, TaskStatus.in_progress, TaskStatus.review},
    TaskStatus.review:      {TaskStatus.done, TaskStatus.in_progress, TaskStatus.in_review},
    TaskStatus.done:        {TaskStatus.in_progress},   # Allow re-open
    TaskStatus.cancelled:   set(),                       # Terminal state
}


def _build_task_code(db: Session) -> str:
    return next_numbered_code(db, "task", prefix="TSK", padding=5)


@router.get("", response_model=List[TaskOut], summary="Listar tareas con filtros")
def list_tasks(
    project_id: Optional[str] = None,
    phase_id: Optional[str] = None,
    assignee_id: Optional[str] = None,
    status: Optional[str] = None,           # acepta un valor o CSV: "in_progress,todo"
    priority: Optional[TaskPriority] = None,
    search: Optional[str] = None,
    overdue_only: bool = False,
    assigned_to_me: bool = False,            # filtrar por usuario autenticado
    limit: Optional[int] = None,             # alias de page_size para compatibilidad
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    response: Response = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    enforce_abac(db, current_user, "task", action="read")

    q = _task_query_for_user(db, current_user).options(
        joinedload(Task.assignee),
        joinedload(Task.reporter),
    )

    # assigned_to_me, employees y subcontractors ven solo sus tareas
    if assigned_to_me or current_user.role in (UserRole.employee, UserRole.subcontractor):
        q = q.filter(Task.assignee_id == current_user.id)
    elif assignee_id:
        q = q.filter(Task.assignee_id == assignee_id)

    if project_id:
        q = q.filter(Task.project_id == project_id)
    if phase_id:
        q = q.filter(Task.phase_id == phase_id)
    if status:
        # Aceptar CSV: "in_progress,todo" o valor único
        status_vals = [s.strip() for s in status.split(",") if s.strip()]
        if len(status_vals) == 1:
            q = q.filter(Task.status == status_vals[0])
        elif status_vals:
            q = q.filter(Task.status.in_(status_vals))
    # limit como alias de page_size
    effective_page_size = limit if limit and limit < page_size else page_size
    if priority:
        q = q.filter(Task.priority == priority)
    if search:
        q = q.filter(
            (Task.title.ilike(f"%{search}%")) |
            (Task.code.ilike(f"%{search}%"))
        )
    if overdue_only:
        from datetime import date
        q = q.filter(
            Task.due_date < date.today(),
            Task.status.not_in([TaskStatus.done, TaskStatus.cancelled]),
        )

    total = q.count()
    tasks = q.offset((page - 1) * effective_page_size).limit(effective_page_size).all()
    if response is not None:
        response.headers["X-Total-Count"] = str(total)
        response.headers["X-Page"] = str(page)
        response.headers["X-Page-Size"] = str(effective_page_size)
    return tasks


@router.get("/kanban/{project_id}", summary="Vista kanban de tareas por estado")
def get_kanban(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Employees and subcontractors may only view kanban of projects they have tasks on
    enforce_abac(db, current_user, "task", action="read")

    project = _project_for_user(db, project_id, current_user)
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
        Task.parent_task_id == None,  # Only top-level
    ).all()

    columns = {s.value: [] for s in TaskStatus if s != TaskStatus.cancelled}
    for task in tasks:
        col = task.status.value
        if col in columns:
            columns[col].append(TaskOut.model_validate(task))

    return columns


@router.get("/{task_id}", response_model=TaskOut, summary="Detalle de tarea")
def get_task(
    task_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    enforce_abac(db, current_user, "task", task_id, action="read")

    task = _task_query_for_user(db, current_user).options(
        joinedload(Task.assignee),
        joinedload(Task.reporter),
        joinedload(Task.comments).joinedload(TaskComment.author),
        joinedload(Task.subtasks),
    ).filter(Task.id == task_id).first()

    if not task:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")

    # Verificar acceso: solo el asignado, el reporter, el PM del proyecto o admin
    if current_user.role != UserRole.admin:
        project = db.query(Project).filter(Project.id == task.project_id).first()
        is_project_pm = project and project.pm_id == current_user.id
        is_task_participant = (task.assignee_id == current_user.id or task.reporter_id == current_user.id)
        if not is_project_pm and not is_task_participant:
            raise HTTPException(status_code=403, detail="No tienes acceso a esta tarea")

    return task


@router.post("", response_model=TaskOut, summary="Crear tarea")
def create_task(
    payload: TaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Employees and subcontractors cannot create tasks
    if current_user.role in (UserRole.employee, UserRole.subcontractor):
        raise HTTPException(status_code=403, detail="No tienes permiso para crear tareas")

    enforce_abac(db, current_user, "task", action="create")

    project = _project_for_user(db, payload.project_id, current_user)
    if not project:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")

    task = Task(
        **payload.model_dump(),
        code=_build_task_code(db),
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
    return task


@router.patch("/{task_id}", response_model=TaskOut, summary="Actualizar tarea")
def update_task(
    task_id: str,
    payload: TaskUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    enforce_abac(db, current_user, "task", task_id, action="update")

    task = _task_query_for_user(db, current_user).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")

    # Verificar acceso: solo el asignado, el PM del proyecto o admin pueden editar
    project = _project_for_user(db, task.project_id, current_user)
    if not project:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")

    if current_user.role != UserRole.admin:
        is_project_pm = project and project.pm_id == current_user.id
        if not is_project_pm and task.assignee_id != current_user.id:
            raise HTTPException(status_code=403, detail="No tienes permiso para editar esta tarea")

    old_assignee_id = task.assignee_id

    # Track status changes and validate transitions
    if payload.status and payload.status != task.status:
        allowed = _TASK_VALID_TRANSITIONS.get(task.status, set())
        if payload.status not in allowed:
            raise HTTPException(
                status_code=400,
                detail=f"Transición de estado no permitida: '{task.status.value}' → '{payload.status.value}'",
            )
        if payload.status == TaskStatus.in_progress:
            task.started_at = datetime.now(timezone.utc)
        elif payload.status == TaskStatus.done:
            task.completed_at = datetime.now(timezone.utc)

    for field, value in payload.model_dump(exclude_unset=True).items():
        if field == "version":
            continue  # handled separately below
        setattr(task, field, value)

    # P1-5: Optimistic locking — check version before applying
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

    # Background: refresh semantic profile when task is done
    if payload.status == TaskStatus.done and task.assignee_id:
        _refresh_profile_bg(background_tasks, db, task.assignee_id)

    # Background: record reassignment feedback for active learning
    if (payload.assignee_id and old_assignee_id
            and payload.assignee_id != old_assignee_id):
        _record_reassign_feedback_bg(background_tasks, db, task_id, "task")

    return task


def _refresh_profile_bg(background_tasks: BackgroundTasks, db: Session, user_id: str):
    """Schedule a semantic profile refresh as a background task."""
    from app.services.semantic_classifier import SemanticAssigner
    from app.db.session import SessionLocal

    def _run():
        _db = SessionLocal()
        try:
            SemanticAssigner(_db).refresh_user_profile(user_id)
        except Exception:
            pass
        finally:
            _db.close()

    background_tasks.add_task(_run)


def _record_reassign_feedback_bg(background_tasks: BackgroundTasks, db: Session,
                                  item_id: str, item_type: str):
    """Record reassignment as implicit negative feedback for the previous assignee."""
    from app.db.session import SessionLocal

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


@router.delete("/{task_id}", summary="Eliminar tarea")
def delete_task(
    task_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_pm),
):
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
    return {"message": "Tarea cancelada"}


@router.post("/{task_id}/comments", response_model=TaskCommentOut, summary="Añadir comentario")
def add_comment(
    task_id: str,
    payload: TaskCommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")

    # Verify access: user must be admin, project PM, assignee, or reporter
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


@router.post("/bulk-dates", summary="Actualizar fechas de múltiples tareas (Gantt drag-and-drop)")
def bulk_update_dates(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_pm),
):
    """
    Actualiza start_date y/o due_date de múltiples tareas en una sola llamada.
    Payload: { updates: [{ id, start_date, due_date }] }
    """
    from app.models.task import Task as TaskModel
    from datetime import date as _date

    def _to_date(v):
        """Convierte string 'YYYY-MM-DD' → datetime.date. None si vacío."""
        if not v:
            return None
        if isinstance(v, _date):
            return v
        try:
            return _date.fromisoformat(str(v)[:10])
        except (ValueError, TypeError):
            return None

    updates = payload.get("updates", [])
    updated = 0
    errors  = []
    for u in updates:
        task = db.query(TaskModel).filter(TaskModel.id == u.get("id")).first()
        if not task:
            errors.append(u.get("id"))
            continue
        if "start_date" in u: task.start_date = _to_date(u["start_date"])
        if "due_date"   in u: task.due_date   = _to_date(u["due_date"])
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


@router.post("/bulk-update", summary="Actualizar estado/asignado/prioridad en múltiples tareas")
def bulk_update_tasks(
    payload: BulkTaskUpdatePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Actualiza status, assignee_id y/o priority de múltiples tareas en una sola llamada.
    Solo procesa tareas a las que el usuario tenga acceso de edición.
    Las transiciones de estado inválidas se reportan en `skipped`.
    """
    if not any([payload.status, payload.assignee_id, payload.priority]):
        raise HTTPException(status_code=422, detail="Debe especificar al menos un campo a actualizar")

    task_ids = list(set(payload.task_ids))  # Deduplicate
    tasks = db.query(Task).options(
        joinedload(Task.assignee)
    ).filter(Task.id.in_(task_ids)).all()

    updated = 0
    skipped = []

    for task in tasks:
        # Access control: admin and PM of the project may bulk-edit; employees and subcontractors cannot
        if current_user.role in (UserRole.employee, UserRole.subcontractor):
            skipped.append({"id": task.id, "reason": "forbidden"})
            continue
        if current_user.role not in (UserRole.admin,):
            project = db.query(Project).filter(Project.id == task.project_id).first()
            if not (project and project.pm_id == current_user.id):
                # Team leads and other roles may still edit tasks assigned to them
                if task.assignee_id != current_user.id:
                    skipped.append({"id": task.id, "reason": "forbidden"})
                    continue

        if payload.status and payload.status != task.status:
            allowed = _TASK_VALID_TRANSITIONS.get(task.status, set())
            if payload.status not in allowed:
                skipped.append({"id": task.id, "reason": f"invalid_transition:{task.status.value}->{payload.status.value}"})
                continue
            if payload.status == TaskStatus.in_progress:
                task.started_at = datetime.now(timezone.utc)
            elif payload.status == TaskStatus.done:
                task.completed_at = datetime.now(timezone.utc)
            task.status = payload.status

        if payload.assignee_id is not None:
            task.assignee_id = payload.assignee_id or None
        if payload.priority is not None:
            task.priority = payload.priority

        task.version = (task.version or 1) + 1
        updated += 1

    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Integrity error in bulk_update_tasks: {str(e)}")
        raise HTTPException(status_code=409, detail="Constraint violation in bulk update.")
    except Exception as e:
        db.rollback()
        logger.error(f"Database error in bulk_update_tasks: {str(e)}")
        raise HTTPException(status_code=503, detail="Database operation failed")
    return {"updated": updated, "skipped": skipped}


@router.post("/{task_id}/cascade-reschedule", summary="Replanificar en cascada todas las tareas dependientes")
def cascade_reschedule(
    task_id: str,
    new_end_date: date = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    When a task's end date (due_date) changes, propagate the shift to all successor tasks
    following Finish-to-Start (FS) dependencies using a BFS traversal.
    Returns the list of rescheduled tasks with their old and new dates.
    """
    from app.models.bookings import TaskDependency, DependencyType
    from collections import deque
    from datetime import timedelta

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

    # Update the root task first
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

    # BFS through FS successors
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
            # New start: day after predecessor's new end + lag
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

    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Integrity error in cascade_reschedule: {str(e)}")
        raise HTTPException(status_code=409, detail="Constraint violation in cascade reschedule.")
    except Exception as e:
        db.rollback()
        logger.error(f"Database error in cascade_reschedule: {str(e)}")
        raise HTTPException(status_code=503, detail="Database operation failed")
    return {"rescheduled": rescheduled, "total_shifted": len(rescheduled)}
