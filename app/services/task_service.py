"""
task_service.py — el API procedural del dominio de tareas.

Es lo que importa `endpoints/tasks.py`. Las piezas que también viven en el
subpaquete `app/services/tasks/` se reexportan desde ahí y no se copian: el
porqué, largo y con nombre y apellidos, está en el bloque de abajo.
"""
from __future__ import annotations
from app.core.errores import ErrorDeDominio

# ── Reexportado del subpaquete `tasks/` ──────────────────────────────────────
#
# Auditoría 2026-08 (hallazgo 18). Aquí había esta nota:
#
#     NOTE: validate_task_transition / apply_status_side_effects /
#     _TASK_VALID_TRANSITIONS / bulk_update_tasks / cascade_reschedule are NOT
#     imported here on purpose: this module defines its own procedural versions
#     below (they carry extra logic such as OKR sync)
#
# **Y era falsa.** Comparadas por AST, ancladas por nombre de función y no por
# número de línea, las cuatro que este módulo duplicaba eran:
#
#   · `validate_task_transition`   → **idéntica** a la del subpaquete;
#   · `apply_status_side_effects`  → **idéntica**. El «OKR sync» que la nota
#                                    invocaba para justificar la copia está en
#                                    las DOS, dentro de esta misma función;
#   · `cascade_reschedule`         → idéntica menos una línea en blanco;
#   · `bulk_update_tasks`          → idéntica menos **un bloque**, y el bloque
#                                    que faltaba era éste:
#
#         try:
#             enforce_abac(db, current_user, "task", task.id, action="update")
#         except HTTPException:
#             skipped.append({"id": task.id, "reason": "abac_denied"})
#             continue
#
# Es decir: la versión local no tenía lógica extra, tenía **una comprobación de
# autorización de menos** — y `endpoints/tasks.py` importa la de aquí.
#
# ── Y aquí va la corrección honesta, porque la primera lectura era falsa ─────
#
# Lo primero que se escribió en este bloque fue que `POST /tasks/bulk-update`
# «se saltaba la evaluación ABAC». **No es cierto, y se comprobó ejecutándolo**:
# con una política `deny` activa sobre `task`, esa ruta devuelve 403 **antes de
# entrar al manejador**, porque la dependencia ABAC de los routers
# (`app/core/abac_dependency.py`) ya la evalúa.
#
# El motivo de que la tape es incómodo: `ABACService.evaluate_access` **no usa
# el `resource_id`**. Lo recibe, lo mete en el detalle de auditoría y no lo mira
# para decidir; `is_policy_applicable` ni lo acepta. La decisión sale del rol,
# del `resource_type` y de los atributos del usuario. Con `action` pasa lo mismo
# y `abac_dependency.py` ya lo dice de sí mismo. Consecuencia: la evaluación
# «por tarea» y la del router dan **siempre el mismo veredicto**, así que la que
# faltaba aquí no podía denegar nada que el router hubiese dejado pasar.
#
# Así que el hueco era **latente, no explotable**: código de autorización que no
# corría, tapado por otra capa que decide lo mismo. Se arregló igual —una
# comprobación que debería estar y no estaba es un defecto aunque no se
# alcance—, y no se vendió como una brecha cerrada.
#
# **Y el defecto de verdad que dejaba a la vista ya está arreglado** (auditoría
# 2026-09): ABAC por recurso concreto no existía, porque `evaluate_access`
# recibía el `resource_id` y no lo miraba. Ahora una regla puede nombrar
# `recurso.<columna>` y `accion`, así que esta llamada por tarea **sí** puede
# denegar algo que la del router deje pasar — la del router no sabe qué fila se
# está tocando. Ver `app/services/abac_recursos.py`.
#
# `bulk_update_dates_record`, en este mismo módulo, sí llamaba a `enforce_abac`:
# la copia había perdido la comprobación en una sola de las dos rutas masivas.
#
# Se reexportan las cuatro y se borran las copias. Los nombres no cambian, así
# que ningún sitio de llamada se toca, y las cuatro pasan a tener **un solo**
# sitio donde arreglarlas.
from app.services.tasks.bulk import bulk_update_tasks  # noqa: F401
from app.services.tasks.core import (  # noqa: F401
    _TASK_VALID_TRANSITIONS,
    apply_status_side_effects,
    validate_task_transition,
)
from app.services.tasks.queries import build_task_list_query  # noqa: F401
from app.services.tasks.scheduling import cascade_reschedule  # noqa: F401

# ─────────────────────────────────────────────────────────────────────────────
# All original imports kept verbatim so the procedural wrappers below compile.
# ─────────────────────────────────────────────────────────────────────────────
import logging
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import BackgroundTasks

from sqlalchemy.orm import Session

from app.models.task import TaskStatus
from app.db.session import SessionLocal
from app.models.bookings import DependencyType, TaskDependency
from app.models.epics import ThreadedComment
from app.models.project import Project, ProjectMember
from app.models.semantic_engine import SemConfig
from app.models.task import Task, TaskComment
from app.models.task import Task as TaskModel
from app.models.task_movement_log import TaskMovementLog
from app.models.user import UserRole
from app.schemas import TaskOut as TaskOutSchema
from app.services.numbering import next_numbered_code
from app.services.semantic_classifier import SemanticAssigner
from datetime import date as _date
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload


def _auto_assign_task_on_create(db: Session, task: Task) -> None:
    """Auto-assign task at creation time when semantic config enables it.

    Honors explicit assignee from payload and only assigns when the semantic
    suggestion is confident enough (needs_review=False).
    """
    if task.assignee_id:
        return

    cfg = db.query(SemConfig).first()
    if not cfg or not bool(getattr(cfg, "auto_assign_tasks", False)):
        return

    members = (
        db.query(ProjectMember)
        .filter(ProjectMember.project_id == task.project_id)
        .all()
    )
    candidate_user_ids = [m.user_id for m in members if getattr(m, "user_id", None)]
    if not candidate_user_ids:
        return

    priority = str(task.priority.value) if hasattr(task.priority, "value") else str(task.priority or "medium")
    suggestion = SemanticAssigner(db).suggest_for_task(
        task.title or "",
        task.description or "",
        candidate_user_ids,
        priority=priority,
    )
    suggested = suggestion.get("suggested_user_id")
    if not suggested or suggestion.get("needs_review", True):
        return
    if suggested not in set(candidate_user_ids):
        return

    task.assignee_id = suggested






# ── Cascade reschedule (BFS) ───────────────────────────────────────────────────



# ── Bulk update ────────────────────────────────────────────────────────────────



# ── Query helpers (scoped to org) ──────────────────────────────────────────────

def task_query_for_user(db: Session, current_user):
    # Superadmin bypass — sin este check, un superadmin de la org "default"
    # nunca vería tareas de otras organizaciones (filtro vacío).
    q = db.query(Task).join(Project, Task.project_id == Project.id)
    is_super = bool(getattr(current_user, "is_superadmin", False))
    if not is_super and current_user.organization_id:
        q = q.filter(Project.organization_id == current_user.organization_id)
    return q


def project_for_user(db: Session, project_id: str, current_user) -> Optional["Project"]:
    # Superadmin bypass (mismo patrón que app/services/tasks/queries.py)
    q = db.query(Project).filter(Project.id == project_id)
    is_super = bool(getattr(current_user, "is_superadmin", False))
    if not is_super and current_user.organization_id:
        q = q.filter(Project.organization_id == current_user.organization_id)
    return q.first()


# ── Kanban ─────────────────────────────────────────────────────────────────────

def get_kanban_payload(db: Session, project_id: str, current_user) -> dict:

    project = project_for_user(db, project_id, current_user)
    if not project:
        raise ErrorDeDominio(status_code=404, detail="Proyecto no encontrado")

    if current_user.role in (UserRole.employee, UserRole.subcontractor):
        has_task = db.query(Task).filter(
            Task.project_id == project_id,
            Task.assignee_id == current_user.id,
        ).first()
        if not has_task:
            raise ErrorDeDominio(status_code=403, detail="No tienes tareas en este proyecto")

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
        raise ErrorDeDominio(status_code=403, detail="No tienes permiso para crear tareas")

    project = project_for_user(db, payload.project_id, current_user)
    if not project:
        raise ErrorDeDominio(status_code=404, detail="Proyecto no encontrado")
    from app.services.issue_type_service import validar_tipo
    validar_tipo(project.id, payload.issue_type, db)

    task = Task(
        **payload.model_dump(),
        code=next_numbered_code(db, "task", prefix="TSK", padding=5),
        reporter_id=current_user.id,
        created_by=current_user.id,
    )
    _auto_assign_task_on_create(db, task)
    try:
        db.add(task)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ErrorDeDominio(status_code=409, detail="Código de tarea duplicado. Inténtalo de nuevo.")
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
        raise ErrorDeDominio(status_code=404, detail="Tarea no encontrada")

    if current_user.role != UserRole.admin:
        project = db.query(Project).filter(Project.id == task.project_id).first()
        is_project_pm = project and project.pm_id == current_user.id
        is_task_participant = (task.assignee_id == current_user.id or task.reporter_id == current_user.id)
        if not is_project_pm and not is_task_participant:
            raise ErrorDeDominio(status_code=403, detail="No tienes acceso a esta tarea")

    return task


# ── Update ─────────────────────────────────────────────────────────────────────

def _autorizar_edicion_de_tarea(task, project, current_user) -> None:
    """Quién puede editar una tarea: admin, el PM del proyecto, o su asignado."""
    if current_user.role == UserRole.admin:
        return
    es_pm = project and project.pm_id == current_user.id
    if not es_pm and task.assignee_id != current_user.id:
        raise ErrorDeDominio(status_code=403, detail="No tienes permiso para editar esta tarea")


def _guardar_con_bloqueo_optimista(db: Session, task, cambios: dict, task_id: str) -> None:
    """Aplica los cambios comprobando la versión, y confirma.

    El bloqueo es **optimista**: no se toma un candado, se compara la versión
    que el cliente creía tener. Si no coincide, alguien guardó por medio y este
    guardado pisaría su trabajo sin que nadie se entere.
    """
    import logging

    logger = logging.getLogger(__name__)

    for campo, valor in cambios.items():
        if campo == "version":
            continue
        setattr(task, campo, valor)

    version_cliente = cambios.get("version")
    if version_cliente is not None and version_cliente != (task.version or 1):
        raise ErrorDeDominio(
            status_code=409,
            detail=(
                f"Conflicto de edición: la tarea fue modificada por otro usuario "
                f"(versión {task.version}). Recarga y reintenta."
            ),
        )
    task.version = (task.version or 1) + 1

    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Integrity error updating task {task_id}: {str(e)}")
        raise ErrorDeDominio(
            status_code=409, detail="Task state conflict. Please reload and try again.",
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Database error updating task {task_id}: {str(e)}")
        raise ErrorDeDominio(status_code=503, detail="Database operation failed")


def _registrar_movimiento(db: Session, task, cambios: dict, estado_anterior, current_user) -> None:
    """Anota el cambio de estado en el registro de movimientos, si lo hubo."""
    nuevo = cambios.get("status")
    if nuevo is None or nuevo == estado_anterior:
        return
    db.add(TaskMovementLog(
        task_id=task.id,
        project_id=task.project_id,
        moved_by_id=current_user.id,
        from_status=str(estado_anterior.value) if estado_anterior else None,
        to_status=str(nuevo.value) if hasattr(nuevo, "value") else str(nuevo),
        reason=cambios.get("move_reason"),
    ))
    db.commit()


def _tipo_de_evento(cambios: dict, asignado_anterior):
    """Qué evento describe mejor esta edición.

    Completar gana sobre reasignar: si una tarea se cierra y se reasigna en el
    mismo guardado, lo que importa contar es que se cerró.
    """
    from app.core.events import EventType

    estado = cambios.get("status")
    if estado and str(estado) in ("done", "completed", "closed"):
        return EventType.TASK_COMPLETED
    asignado = cambios.get("assignee_id")
    if asignado and asignado != asignado_anterior:
        return EventType.TASK_ASSIGNED
    return EventType.TASK_UPDATED


def update_task_record(db: Session, task_id: str, payload, current_user):
    """Actualiza una tarea: autoriza, valida la transición, guarda y anota.

    Auditoría 2026-09 (hallazgo 18): eran 83 líneas y complejidad 14 con la
    autorización, el bloqueo optimista, el registro de movimientos y la
    selección de evento mezclados. Cada fase tiene ahora su nombre, y el orden
    —que importa— se lee en el cuerpo.
    """
    task = task_query_for_user(db, current_user).filter(Task.id == task_id).first()
    if not task:
        raise ErrorDeDominio(status_code=404, detail="Tarea no encontrada")

    project = project_for_user(db, task.project_id, current_user)
    if not project:
        raise ErrorDeDominio(status_code=404, detail="Proyecto no encontrado")

    _autorizar_edicion_de_tarea(task, project, current_user)
    from app.services.issue_type_service import validar_tipo
    validar_tipo(project.id, getattr(payload, "issue_type", None), db)

    # Se capturan **antes** de mutar nada: después, `task` ya no sabe de dónde
    # venía.
    asignado_anterior = task.assignee_id
    estado_anterior = task.status

    if payload.status and payload.status != task.status:
        validate_task_transition(task.status, payload.status)
        apply_status_side_effects(task, payload.status)

    cambios = payload.model_dump(exclude_unset=True)
    _guardar_con_bloqueo_optimista(db, task, cambios, task_id)
    db.refresh(task)

    _registrar_movimiento(db, task, cambios, estado_anterior, current_user)

    from app.core.events import emit

    emit(
        db, _tipo_de_evento(cambios, asignado_anterior),
        {
            "title": task.title, "status": str(task.status),
            "assignee_id": task.assignee_id, "project_id": task.project_id,
            **cambios,
        },
        actor=current_user, resource_type="task", resource_id=task.id,
        project_id=task.project_id,
    )
    return task, asignado_anterior


# ── Cancel ─────────────────────────────────────────────────────────────────────

def cancel_task_record(db: Session, task_id: str, current_user=None) -> dict:
    """Soft-cancel a task by id.

    Audit #62: when current_user is supplied and is not a superadmin, the
    Task lookup is org-scoped via Project.organization_id to prevent
    cross-tenant cancellation by guessing the id.
    """
    import logging

    logger = logging.getLogger(__name__)

    q = db.query(Task).filter(Task.id == task_id)
    if current_user is not None and not getattr(current_user, "is_superadmin", False) and getattr(current_user, "organization_id", None):
        q = q.join(Project, Task.project_id == Project.id).filter(
            Project.organization_id == current_user.organization_id
        )
    task = q.first()
    if not task:
        raise ErrorDeDominio(status_code=404, detail="Tarea no encontrada")
    if task.status == TaskStatus.cancelled:
        raise ErrorDeDominio(status_code=400, detail="La tarea ya esta cancelada")
    task.status = TaskStatus.cancelled
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Integrity error cancelling task {task_id}: {str(e)}")
        raise ErrorDeDominio(status_code=409, detail="Cannot cancel task. State conflict.")
    except Exception as e:
        db.rollback()
        logger.error(f"Database error cancelling task {task_id}: {str(e)}")
        raise ErrorDeDominio(status_code=503, detail="Database operation failed")
    from app.core.events import emit, EventType
    emit(db, EventType.TASK_DELETED,
         {"title": task.title, "project_id": task.project_id, "reason": "cancelled"},
         resource_type="task", resource_id=task_id, project_id=task.project_id)
    return {"ok": True, "message": "Tarea cancelada correctamente"}


# ── Comment ────────────────────────────────────────────────────────────────────

def add_comment_record(db: Session, task_id: str, payload, current_user):
    import logging

    logger = logging.getLogger(__name__)

    # Audit #62: scope Task lookup by org via Project to prevent cross-tenant
    # comments on tasks whose id is guessed.
    q = db.query(Task).filter(Task.id == task_id)
    if not getattr(current_user, "is_superadmin", False) and getattr(current_user, "organization_id", None):
        q = q.join(Project, Task.project_id == Project.id).filter(
            Project.organization_id == current_user.organization_id
        )
    task = q.first()
    if not task:
        raise ErrorDeDominio(status_code=404, detail="Tarea no encontrada")

    if current_user.role != UserRole.admin:
        project = db.query(Project).filter(Project.id == task.project_id).first()
        is_project_pm = project and project.pm_id == current_user.id
        is_task_participant = (task.assignee_id == current_user.id or task.reporter_id == current_user.id)
        if not is_project_pm and not is_task_participant:
            raise ErrorDeDominio(status_code=403, detail="No tienes acceso a esta tarea")

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
        raise ErrorDeDominio(status_code=409, detail="Cannot add comment. Conflict.")
    except Exception as e:
        db.rollback()
        logger.error(f"Database error adding comment to task {task_id}: {str(e)}")
        raise ErrorDeDominio(status_code=503, detail="Database operation failed")
    db.refresh(comment)
    return comment


# ── Bulk dates ─────────────────────────────────────────────────────────────────

def _a_fecha(valor):
    """Una fecha, o `None` si no se puede leer. No levanta.

    Aquí un valor ilegible no puede tumbar una actualización en masa: la fila se
    queda sin fecha y las demás siguen.
    """
    if not valor:
        return None
    if isinstance(valor, _date):
        return valor
    try:
        return _date.fromisoformat(str(valor)[:10])
    except (ValueError, TypeError):
        return None


def _aplicar_fechas_a_tarea(db: Session, cambio: dict, current_user) -> Optional[dict]:
    """Aplica las fechas a una tarea. Devuelve el error, o `None` si fue bien.

    G5: ABAC se comprueba **tarea a tarea**. Una actualización en masa no es una
    excepción al control de acceso; sería justo la forma de saltárselo.
    """
    from app.core.abac_enforce import enforce_abac

    task_id = cambio.get("id")
    task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
    if not task:
        return {"id": task_id, "reason": "not_found"}

    if current_user:
        try:
            enforce_abac(db, current_user, "task", task.id, action="update")
        except (HTTPException, ErrorDeDominio):
            return {"id": task.id, "reason": "abac_denied"}

    if "start_date" in cambio:
        task.start_date = _a_fecha(cambio["start_date"])
    if "due_date" in cambio:
        task.due_date = _a_fecha(cambio["due_date"])
    return None


def bulk_update_dates_record(db: Session, updates: list, current_user=None) -> dict:
    """Mueve las fechas de varias tareas de una vez.

    Las tareas que fallan **no detienen** al resto: se devuelven en `errors` con
    su motivo. Es lo que necesita un Gantt donde el usuario arrastra un bloque y
    algunas de las tareas no son suyas.
    """
    import logging

    logger = logging.getLogger(__name__)

    errors = []
    actualizadas = 0
    for cambio in updates:
        error = _aplicar_fechas_a_tarea(db, cambio, current_user)
        if error:
            errors.append(error)
        else:
            actualizadas += 1

    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Integrity error in bulk_update_dates: {str(e)}")
        raise ErrorDeDominio(status_code=409, detail="Constraint violation in bulk date update.")
    except Exception as e:
        db.rollback()
        logger.error(f"Database error in bulk_update_dates: {str(e)}")
        raise ErrorDeDominio(status_code=503, detail="Database operation failed")

    return {"updated": actualizadas, "errors": errors}


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
            logging.getLogger(__name__).warning("Failed to mark SemAssignment rejection for item=%s type=%s", item_id, item_type, exc_info=True)
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
            logging.getLogger(__name__).warning("SemanticAssigner.refresh_user_profile failed for user=%s", user_id, exc_info=True)
        finally:
            _db.close()

    background_tasks.add_task(_run)


# ── Task Dependencies ──────────────────────────────────────────────────────────

def list_task_dependencies(db: Session, project_id: str) -> list:
    """Return all task dependencies for a project, with predecessor/successor loaded."""
    q = (
        db.query(TaskDependency)
        .options(
            joinedload(TaskDependency.predecessor),
            joinedload(TaskDependency.successor),
        )
        .join(Task, TaskDependency.predecessor_id == Task.id)
        .filter(Task.project_id == project_id)
        .filter(TaskDependency.is_active == True)
    )
    return [
        {
            "id": d.id,
            "predecessor_id": d.predecessor_id,
            "successor_id": d.successor_id,
            "dependency_type": d.dependency_type,
            "lag_days": d.lag_days,
        }
        for d in q.all()
    ]


def _cierra_un_ciclo(db: Session, predecessor_id: str, successor_id: str) -> bool:
    """¿Ya se llega de `successor_id` a `predecessor_id` por dependencias activas?"""
    pendientes, vistos = [successor_id], set()
    while pendientes:
        actual = pendientes.pop()
        if actual == predecessor_id:
            return True
        if actual in vistos:
            continue
        vistos.add(actual)
        pendientes += [s for (s,) in db.query(TaskDependency.successor_id).filter(
            TaskDependency.predecessor_id == actual, TaskDependency.is_active.is_(True)).all()]
    return False


def create_task_dependency(
    db: Session,
    predecessor_id: str,
    successor_id: str,
    dependency_type: str,
    lag_days: int,
    created_by: str,
) -> dict:
    """
    Create a dependency between two tasks.
    Raises 400 on self-reference, 409 if it already exists.
    """
    # Revisión 2026-11: los tipos son los del Gantt y el autoplanificador (FS/SS/FF/SF, la columna es
    # un enum). La página de dependencias mandaba tipos de Jira que no se podían guardar; si llegan,
    # «bloquea» es FS y «bloqueada por» es FS al revés.
    tipo = getattr(dependency_type, "value", dependency_type)
    if tipo == "blocks":
        tipo = "FS"
    elif tipo == "blocked_by":
        tipo, predecessor_id, successor_id = "FS", successor_id, predecessor_id
    try:
        dependency_type = DependencyType(tipo)
    except ValueError:
        raise ErrorDeDominio(400, f"Tipo de dependencia no válido: {tipo} (FS, SS, FF o SF)")
    if predecessor_id == successor_id:
        raise ErrorDeDominio(400, "Una tarea no puede depender de sí misma")
    if _cierra_un_ciclo(db, predecessor_id, successor_id):
        raise ErrorDeDominio(400, "Esa dependencia cerraría un ciclo: la tarea siguiente ya va antes que la anterior")
    existing = (
        db.query(TaskDependency)
        .filter(
            TaskDependency.predecessor_id == predecessor_id,
            TaskDependency.successor_id == successor_id,
        ).first()
    )
    if existing and existing.is_active:
        raise ErrorDeDominio(409, "La dependencia ya existe")
    if existing and not existing.is_active:
        existing.is_active = True
        existing.dependency_type = dependency_type
        existing.lag_days = lag_days
        db.commit()
        db.refresh(existing)
        return {
            "id": existing.id,
            "predecessor_id": existing.predecessor_id,
            "successor_id": existing.successor_id,
            "dependency_type": existing.dependency_type,
            "lag_days": existing.lag_days,
        }
    dep = TaskDependency(
        predecessor_id=predecessor_id,
        successor_id=successor_id,
        dependency_type=dependency_type,
        lag_days=lag_days,
        created_by=created_by,
    )
    db.add(dep)
    db.commit()
    db.refresh(dep)
    return {
        "id": dep.id,
        "predecessor_id": dep.predecessor_id,
        "successor_id": dep.successor_id,
        "dependency_type": dep.dependency_type,
        "lag_days": dep.lag_days,
    }


def delete_task_dependency(db: Session, dep_id: str) -> dict:
    """Delete a task dependency by id. Raises 404 if not found."""
    dep = db.query(TaskDependency).filter(TaskDependency.id == dep_id, TaskDependency.is_active == True).first()
    if not dep:
        raise ErrorDeDominio(404, "Dependencia no encontrada")
    dep.is_active = False
    db.commit()
    return {"ok": True, "message": "Dependencia eliminada correctamente"}


# ── Extracted query helpers (moved from endpoint layer) ───────────────────────


def get_task_by_id(
    task_id: str,
    db: Session,
    org_id: Optional[str] = None,
) -> Optional[Task]:
    """Return a Task by id, optionally scoped to an organisation.

    The org scope is applied via a join on Project when org_id is provided,
    mirroring the behaviour of task_query_for_user() without requiring a full
    user object.
    """
    q = db.query(Task)
    if org_id:
        q = q.join(Project, Task.project_id == Project.id).filter(
            Project.organization_id == org_id
        )
    return q.filter(Task.id == task_id).first()


def get_project_member_ids(project_id: str, db: Session) -> list[str]:
    """Return user_ids of all members of a project."""
    members = (
        db.query(ProjectMember)
        .filter(ProjectMember.project_id == project_id, ProjectMember.is_active == True)
        .all()
    )
    return [m.user_id for m in members if getattr(m, "user_id", None)]


def get_tasks_for_project(
    project_id: str,
    db: Session,
    status: Optional[str] = None,
) -> list[Task]:
    """Return all tasks for a project, optionally filtered by status."""
    q = db.query(Task).filter(Task.project_id == project_id)
    if status:
        q = q.filter(Task.status == status)
    return q.all()


def get_tasks_for_sprint(sprint_id: str, db: Session) -> list[Task]:
    """Return all tasks assigned to a sprint.

    Auditoria 2026-08: esto filtraba por `Task.sprint_id`, y **esa columna no
    existe**. Una tarea se enlaza a un sprint por la tabla `sprint_tasks`
    (`SprintTask`), asi que la consulta reventaba con `AttributeError` y
    «las tareas de un sprint» no se podian listar.
    """
    from app.models.sprints import SprintTask

    return (
        db.query(Task)
        .join(SprintTask, SprintTask.task_id == Task.id)
        .filter(SprintTask.sprint_id == sprint_id)
        .all()
    )


def get_threaded_comments_for_task(
    task_id: str,
    db: Session,
) -> list[ThreadedComment]:
    """Return threaded comments linked to a task, ordered oldest-first."""
    return (
        db.query(ThreadedComment)
        .filter(
            ThreadedComment.entity_type == "task",
            ThreadedComment.entity_id == task_id,
        )
        .order_by(ThreadedComment.created_at.asc())
        .all()
    )


def get_task_movement_log(
    task_id: str,
    db: Session,
    limit: int = 50,
) -> list[TaskMovementLog]:
    """Return movement-log entries for a task, newest-first, up to *limit* rows."""
    return (
        db.query(TaskMovementLog)
        .options(joinedload(TaskMovementLog.moved_by))
        .filter(TaskMovementLog.task_id == task_id)
        .order_by(TaskMovementLog.moved_at.desc())
        .limit(limit)
        .all()
    )


def get_sem_config(db: Session) -> Optional[SemConfig]:
    """Return the first (global) SemConfig row, or None if not configured."""
    return db.query(SemConfig).first()
