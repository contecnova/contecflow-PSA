from fastapi import APIRouter, Depends, HTTPException, Query, Body, BackgroundTasks, Response
from sqlalchemy.orm import Session, joinedload
from typing import Optional, List
from datetime import date
import logging

logger = logging.getLogger(__name__)

from app.db.session import get_db
from app.core.abac_enforce import enforce_abac
from app.core.deps import get_current_user, require_admin_or_pm
from app.models.user import User, UserRole
from app.models.task import Task, TaskStatus, TaskPriority, TaskComment
from app.models.project import Project
from app.schemas import (
    TaskCreate, TaskUpdate, TaskOut, TaskCommentCreate, TaskCommentOut, BulkTaskUpdatePayload
)
from app.services.task_service import (
    TASK_VALID_TRANSITIONS,
    validate_task_transition,
    apply_status_side_effects,
    cascade_reschedule as svc_cascade_reschedule,
    bulk_update_tasks as svc_bulk_update_tasks,
    task_query_for_user,
    get_kanban_payload,
    get_task_record,
    create_task_record,
    update_task_record,
    cancel_task_record,
    add_comment_record,
    bulk_update_dates_record,
    record_reassign_feedback_bg,
)

router = APIRouter()


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

    q = task_query_for_user(db, current_user).options(
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
        from datetime import date as _date
        q = q.filter(
            Task.due_date < _date.today(),
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
    enforce_abac(db, current_user, "task", action="read")
    return get_kanban_payload(db, project_id, current_user)


@router.get("/{task_id}", response_model=TaskOut, summary="Detalle de tarea")
def get_task(
    task_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    enforce_abac(db, current_user, "task", task_id, action="read")
    return get_task_record(db, task_id, current_user)


@router.post("", response_model=TaskOut, summary="Crear tarea")
def create_task(
    payload: TaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    enforce_abac(db, current_user, "task", action="create")
    return create_task_record(db, payload, current_user)


@router.patch("/{task_id}", response_model=TaskOut, summary="Actualizar tarea")
def update_task(
    task_id: str,
    payload: TaskUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    enforce_abac(db, current_user, "task", task_id, action="update")
    task, old_assignee_id = update_task_record(db, task_id, payload, current_user)

    # Background: refresh semantic profile when task is done
    if payload.status == TaskStatus.done and task.assignee_id:
        _refresh_profile_bg(background_tasks, db, task.assignee_id)

    # Background: record reassignment feedback for active learning
    if (payload.assignee_id and old_assignee_id
            and payload.assignee_id != old_assignee_id):
        record_reassign_feedback_bg(background_tasks, db, task_id, "task")

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



@router.delete("/{task_id}", summary="Eliminar tarea")
def delete_task(
    task_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_pm),
):
    return cancel_task_record(db, task_id)


@router.post("/{task_id}/comments", response_model=TaskCommentOut, summary="Añadir comentario")
def add_comment(
    task_id: str,
    payload: TaskCommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return add_comment_record(db, task_id, payload, current_user)


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
    updates = payload.get("updates", [])
    return bulk_update_dates_record(db, updates)


@router.post("/bulk-update", summary="Actualizar estado/asignado/prioridad en múltiples tareas")
def bulk_update_tasks(
    payload: BulkTaskUpdatePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not any([payload.status, payload.assignee_id, payload.priority]):
        raise HTTPException(status_code=422, detail="Debe especificar al menos un campo a actualizar")
    updates = {
        "status": payload.status,
        "assignee_id": payload.assignee_id,
        "priority": payload.priority,
    }
    return svc_bulk_update_tasks(payload.task_ids, updates, current_user, db)


@router.post("/{task_id}/cascade-reschedule", summary="Replanificar en cascada todas las tareas dependientes")
def cascade_reschedule(
    task_id: str,
    new_end_date: date = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc_cascade_reschedule(task_id, new_end_date, db)

