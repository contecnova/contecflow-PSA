from fastapi import APIRouter, Depends, HTTPException, Query, Body, BackgroundTasks, Response
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date
import logging

logger = logging.getLogger(__name__)

from app.db.session import get_db
from app.core.abac_enforce import enforce_abac
from app.core.deps import get_current_user, require_admin_or_pm
from app.core.responses import APIResponse, APIListResponse
from app.models.user import User
from app.models.task import TaskStatus, TaskPriority
from app.schemas import (
    TaskCreate, TaskUpdate, TaskOut, TaskCommentCreate, TaskCommentOut, BulkTaskUpdatePayload
)
from app.schemas.tasks import TaskMovementLogOut
from app.services.task_service import (
    cascade_reschedule as svc_cascade_reschedule,
    bulk_update_tasks as svc_bulk_update_tasks,
    build_task_list_query,
    get_kanban_payload,
    get_task_record,
    create_task_record,
    update_task_record,
    cancel_task_record,
    add_comment_record,
    bulk_update_dates_record,
    record_reassign_feedback_bg,
    refresh_profile_bg as _refresh_profile_bg,
    list_task_dependencies as svc_list_task_dependencies,
    create_task_dependency as svc_create_task_dependency,
    delete_task_dependency as svc_delete_task_dependency,
    get_project_member_ids as svc_get_project_member_ids,
    get_threaded_comments_for_task,
    get_task_movement_log,
    get_sem_config,
)
from app.services.semantic_engine_service import enrich_suggestion
from app.services.semantic_classifier import SemanticAssigner

router = APIRouter()


@router.post("/suggest-assignee", summary="[DEPRECATED] Sugerir asignación de tarea — usar /semantic/suggest/task")
def suggest_task_assignee(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    response: Response = None,
):
    # Deprecated: canonical path is POST /semantic/suggest/task (returns flat suggestion + records SemAssignment)
    if response is not None:
        response.headers["Deprecation"] = "true"
        response.headers["Link"] = '</api/v1/semantic/suggest/task>; rel="successor-version"'

    enforce_abac(db, current_user, "task", action="read")

    title = str(payload.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=422, detail="title es obligatorio")

    description = str(payload.get("description") or "")
    project_id = payload.get("project_id")
    priority = str(payload.get("priority") or "medium")
    candidate_user_ids = payload.get("candidate_user_ids")

    if not candidate_user_ids and project_id:
        candidate_user_ids = svc_get_project_member_ids(project_id, db)

    suggestion = SemanticAssigner(db).suggest_for_task(
        title,
        description,
        candidate_user_ids,
        priority=priority,
    )
    suggestion = enrich_suggestion(db, suggestion)
    sem_cfg = get_sem_config(db)
    semantic_auto_assign_enabled = bool(getattr(sem_cfg, "auto_assign_tasks", False)) if sem_cfg else False

    return APIResponse.ok(data={
        "requires_confirmation": True,
        "semantic_auto_assign_enabled": semantic_auto_assign_enabled,
        "suggestion": suggestion,
        "confirmation_hint": "Confirma asignando assignee_id en POST /tasks o PATCH /tasks/{task_id}",
    })


@router.get("", response_model=APIListResponse[TaskOut], summary="Listar tareas con filtros")
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

    # limit como alias de page_size
    effective_page_size = limit if limit and limit < page_size else page_size

    q = build_task_list_query(
        db, current_user,
        assigned_to_me=assigned_to_me,
        assignee_id=assignee_id,
        project_id=project_id,
        phase_id=phase_id,
        status=status,
        priority=priority,
        search=search,
        overdue_only=overdue_only,
    )

    total = q.count()
    tasks = q.offset((page - 1) * effective_page_size).limit(effective_page_size).all()
    if response is not None:
        response.headers["X-Total-Count"] = str(total)
        response.headers["X-Page"] = str(page)
        response.headers["X-Page-Size"] = str(effective_page_size)
    return APIListResponse.ok(items=tasks, total=total, page=page, page_size=effective_page_size)


@router.get("/kanban/{project_id}", summary="Vista kanban de tareas por estado")
def get_kanban(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    enforce_abac(db, current_user, "task", action="read")
    return APIResponse.ok(data=get_kanban_payload(db, project_id, current_user))


# ── Task Dependencies ─────────────────────────────────────────────────────────
#
# Auditoria 2026-08. Este bloque estaba DESPUES de `@router.get("/{task_id}")`,
# y en FastAPI gana la primera ruta que encaja: `GET /tasks/dependencies` iba a
# `get_task(task_id="dependencies")` y respondia
# **404 «Tarea no encontrada»** — el endpoint era inalcanzable y el mensaje
# mandaba a buscar una tarea que falta en vez de un problema de rutas.
#
# Por eso va aqui arriba: las rutas con segmento LITERAL tienen que declararse
# antes que las que llevan `{parametro}` en la misma posicion. Hay un test
# estructural (`tests/test_rutas_tapadas.py`) que lo comprueba para toda la
# aplicacion.

# Compatibilidad: /tasks/dependencies → /task-dependencies/{project_id}

@router.get("/dependencies", response_model=APIListResponse[dict], summary="Listar dependencias de tareas")
def list_dependencies(
    project_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not project_id:
        # Si no se pasa project_id, devolver array vacío para evitar 404 en frontend
        return APIListResponse.ok(items=[], total=0)
    items = svc_list_task_dependencies(db, project_id)
    return APIListResponse.ok(items=items, total=len(items))


# Compatibilidad: /tasks/dependencies/{project_id}
@router.get("/dependencies/{project_id}", response_model=APIListResponse[dict], summary="Listar dependencias de tareas por proyecto (compatibilidad)")
def list_dependencies_by_project(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items = svc_list_task_dependencies(db, project_id)
    return APIListResponse.ok(items=items, total=len(items))


@router.post("/dependencies", summary="Crear dependencia entre tareas", status_code=201)
def create_dependency(
    predecessor_id: str = Body(...),
    successor_id: str = Body(...),
    dependency_type: str = Body("FS"),
    lag_days: int = Body(0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return APIResponse.ok(data=svc_create_task_dependency(db, predecessor_id, successor_id, dependency_type, lag_days, current_user.id))


@router.delete("/dependencies/{dep_id}", summary="Eliminar dependencia entre tareas")
def delete_dependency(
    dep_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    # Auditoria 2026-09: el unico control era `enforce_abac`, que sin
    # politicas activas no comprueba nada. Una dependencia entre tareas es
    # estructura de proyecto: la decide quien planifica, igual que
    # `POST /epics/{id}/dependencies/{id}`, que ya exige lo mismo.
    _: User = Depends(require_admin_or_pm),
):
    enforce_abac(db, current_user, "task_dependency", dep_id, action="delete")
    return APIResponse.ok(data=svc_delete_task_dependency(db, dep_id))



@router.get("/{task_id}", response_model=APIResponse[TaskOut], summary="Detalle de tarea")
def get_task(
    task_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    enforce_abac(db, current_user, "task", task_id, action="read")
    task = get_task_record(db, task_id, current_user)

    # Merge threaded comments (Mentions page) into the same payload consumed
    # by task detail so users see a single unified conversation history.
    task_out = TaskOut.model_validate(task).model_dump(mode="python")
    threaded = get_threaded_comments_for_task(task_id, db)
    if threaded:
        merged = list(task_out.get("comments") or [])
        for c in threaded:
            content = c.content if not c.parent_id else f"↳ {c.content}"
            merged.append(
                {
                    "id": c.id,
                    "task_id": task_id,
                    "author": None,
                    "content": content,
                    "created_at": c.created_at,
                }
            )
        merged.sort(key=lambda x: x.get("created_at") or "")
        task_out["comments"] = merged

    return APIResponse.ok(data=task_out)


@router.post("", response_model=APIResponse[TaskOut], summary="Crear tarea")
def create_task(
    payload: TaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    enforce_abac(db, current_user, "task", action="create")
    return APIResponse.ok(data=create_task_record(db, payload, current_user))


@router.patch("/{task_id}", response_model=APIResponse[TaskOut], summary="Actualizar tarea")
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

    return APIResponse.ok(data=task)


@router.get("/{task_id}/movement-log", response_model=APIListResponse[TaskMovementLogOut], summary="Historial de movimientos de tarea")
def get_movement_log(
    task_id: str,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Devuelve el historial de movimientos (cambios de estado) de una tarea, ordenado del más reciente al más antiguo."""
    items = get_task_movement_log(task_id, db, limit=limit)
    return APIListResponse.ok(items=items, page_size=limit)


@router.delete("/{task_id}", summary="Eliminar tarea")
def delete_task(
    task_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_pm),
):
    enforce_abac(db, current_user, "task", task_id, action="delete")
    return APIResponse.ok(data=cancel_task_record(db, task_id, current_user))


@router.post("/{task_id}/comments", response_model=APIResponse[TaskCommentOut], summary="Añadir comentario")
def add_comment(
    task_id: str,
    payload: TaskCommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return APIResponse.ok(data=add_comment_record(db, task_id, payload, current_user))


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
    return APIResponse.ok(data=bulk_update_dates_record(db, updates, current_user))


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
    return APIResponse.ok(data=svc_bulk_update_tasks(payload.task_ids, updates, current_user, db))


@router.post("/{task_id}/cascade-reschedule", summary="Replanificar en cascada todas las tareas dependientes")
def cascade_reschedule(
    task_id: str,
    new_end_date: date = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return APIResponse.ok(data=svc_cascade_reschedule(task_id, new_end_date, db))
