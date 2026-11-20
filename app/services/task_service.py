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
from app.core.codigos_de_error import error as error_con_codigo

if TYPE_CHECKING:
    from app.core.tareas_diferidas import ProgramadorDeTareas

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
        raise error_con_codigo(404, "no_encontrado", detail="Proyecto no encontrado", que="proyecto")

    if current_user.role in (UserRole.employee, UserRole.subcontractor):
        has_task = db.query(Task).filter(
            Task.project_id == project_id,
            Task.assignee_id == current_user.id,
        ).first()
        if not has_task:
            raise error_con_codigo(403, "sin_tareas_en_proyecto")

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

def _trabaja_en_el_proyecto(db: Session, project_id: str, user) -> bool:
    """Miembro activo del equipo (`project_members`) o con tareas asignadas en él,
    y el proyecto dentro de su alcance (`scope_projects_query`, que aplica los
    vetos por proyecto)."""
    from app.services.project_service import scope_projects_query
    if not scope_projects_query(db.query(Project.id), db, user).filter(Project.id == project_id).first():
        return False
    if db.query(ProjectMember.id).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user.id,
        ProjectMember.is_active.is_(True),
    ).first():
        return True
    return db.query(Task.id).filter(Task.project_id == project_id, Task.assignee_id == user.id).first() is not None


def _exigir_alta_en_su_proyecto(db: Session, payload, project, current_user) -> None:
    """Externos como internos (16-11-2026). El empleado y el subcontratado crean
    tareas SOLO en los proyectos donde trabajan; fuera, 404 (no se confirma que
    el proyecto exista). Antes los dos tenían el alta cerrada del todo.

    Lo que cuelga de la tarea ha de ser del mismo proyecto (fase y tarea padre),
    y el subcontratado solo la asigna a alguien que ve
    (`politica_de_visibilidad.ids_de_personas_visibles`)."""
    if not _trabaja_en_el_proyecto(db, project.id, current_user):
        raise error_con_codigo(404, "no_encontrado", detail="Proyecto no encontrado", que="proyecto")
    if payload.parent_task_id and not db.query(Task.id).filter(
            Task.id == payload.parent_task_id, Task.project_id == project.id).first():
        raise error_con_codigo(404, "no_encontrado", detail="Tarea padre no encontrada", que="tarea_padre")
    if payload.phase_id:
        from app.models.project import ProjectPhase
        if not db.query(ProjectPhase.id).filter(
                ProjectPhase.id == payload.phase_id, ProjectPhase.project_id == project.id).first():
            raise error_con_codigo(404, "no_encontrado", detail="Fase no encontrada", que="fase")
    if payload.assignee_id and payload.assignee_id != current_user.id:
        from app.services.politica_de_visibilidad import es_externo, ids_de_personas_visibles
        if es_externo(current_user) and payload.assignee_id not in ids_de_personas_visibles(db, current_user):
            raise error_con_codigo(404, "no_encontrado", detail="Usuario no encontrado", que="usuario")


def _exigir_quien_externaliza(payload, current_user) -> None:
    """Migracion 189: externalizar una tarea a una empresa es de gestion (admin,
    PM, team lead); el empleado y el externo no la mueven a un proveedor."""
    if getattr(current_user, "is_superadmin", False):
        return
    datos = payload.model_dump(exclude_unset=True)
    if not (datos.get("supplier_id") or datos.get("supplier_work_package_id")):
        return
    if current_user.role in (UserRole.employee, UserRole.subcontractor, UserRole.hr):
        raise error_con_codigo(403, "sin_permiso")


def create_task_record(db: Session, payload, current_user):

    project = project_for_user(db, payload.project_id, current_user)
    if not project:
        raise error_con_codigo(404, "no_encontrado", detail="Proyecto no encontrado", que="proyecto")
    if not getattr(current_user, "is_superadmin", False) and current_user.role in (
            UserRole.employee, UserRole.subcontractor):
        _exigir_alta_en_su_proyecto(db, payload, project, current_user)
    _exigir_quien_externaliza(payload, current_user)
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
        raise error_con_codigo(409, "conflicto_concurrente", detail="Código de tarea duplicado. Inténtalo de nuevo.")
    db.refresh(task)
    from app.core.events import emit, EventType
    emit(db, EventType.TASK_CREATED,
         {"title": task.title, "status": str(task.status), "assignee_id": task.assignee_id,
          "project_id": task.project_id, "code": task.code},
         actor=current_user, resource_type="task", resource_id=task.id,
         project_id=task.project_id)
    from app.services.planificador.servicio import recalcular_si_procede
    recalcular_si_procede(db, task.project_id)
    db.refresh(task)
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
        raise error_con_codigo(404, "no_encontrado", detail="Tarea no encontrada", que="tarea")

    if current_user.role != UserRole.admin:
        project = db.query(Project).filter(Project.id == task.project_id).first()
        is_project_pm = project and project.pm_id == current_user.id
        is_task_participant = (task.assignee_id == current_user.id or task.reporter_id == current_user.id)
        if not is_project_pm and not is_task_participant:
            raise error_con_codigo(403, "sin_acceso_tarea")

    return task


# ── Update ─────────────────────────────────────────────────────────────────────

def _autorizar_edicion_de_tarea(task, project, current_user) -> None:
    """Quién puede editar una tarea: admin, el PM del proyecto, o su asignado."""
    if current_user.role == UserRole.admin:
        return
    es_pm = project and project.pm_id == current_user.id
    if not es_pm and task.assignee_id != current_user.id:
        raise error_con_codigo(403, "sin_permiso", detail="No tienes permiso para editar esta tarea")


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
        raise error_con_codigo(409, "conflicto_concurrente", detail=f"Conflicto de edición: la tarea fue modificada por otro usuario "
                f"(versión {task.version}). Recarga y reintenta.")
    task.version = (task.version or 1) + 1

    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Integrity error updating task {task_id}: {str(e)}")
        raise error_con_codigo(409, "conflicto_concurrente", detail="Task state conflict. Please reload and try again.")
    except Exception as e:
        db.rollback()
        logger.error(f"Database error updating task {task_id}: {str(e)}")
        raise error_con_codigo(503, "operacion_bd_fallida", detail="Database operation failed")


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


#: Campos de una tarea que cambian su plan (duración, fechas, calendario o restricción).
_CAMPOS_QUE_PLANIFICAN = frozenset({
    "start_date", "due_date", "estimated_hours", "assignee_id", "status",
    "constraint_type", "constraint_date",
})


def update_task_record(db: Session, task_id: str, payload, current_user):
    """Actualiza una tarea: autoriza, valida la transición, guarda y anota.

    Auditoría 2026-09 (hallazgo 18): eran 83 líneas y complejidad 14 con la
    autorización, el bloqueo optimista, el registro de movimientos y la
    selección de evento mezclados. Cada fase tiene ahora su nombre, y el orden
    —que importa— se lee en el cuerpo.
    """
    task = task_query_for_user(db, current_user).filter(Task.id == task_id).first()
    if not task:
        raise error_con_codigo(404, "no_encontrado", detail="Tarea no encontrada", que="tarea")

    project = project_for_user(db, task.project_id, current_user)
    if not project:
        raise error_con_codigo(404, "no_encontrado", detail="Proyecto no encontrado", que="proyecto")

    _autorizar_edicion_de_tarea(task, project, current_user)
    _exigir_quien_externaliza(payload, current_user)
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

    # Rev. 173: lo que cambia el plan recalcula el camino crítico del proyecto.
    if _CAMPOS_QUE_PLANIFICAN & set(cambios):
        from app.services.planificador.servicio import recalcular_si_procede
        recalcular_si_procede(db, task.project_id)
        db.refresh(task)

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
        raise error_con_codigo(404, "no_encontrado", detail="Tarea no encontrada", que="tarea")
    if task.status == TaskStatus.cancelled:
        raise error_con_codigo(400, "tarea_ya_cancelada", detail="La tarea ya esta cancelada")
    task.status = TaskStatus.cancelled
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Integrity error cancelling task {task_id}: {str(e)}")
        raise error_con_codigo(409, "conflicto_concurrente", detail="Cannot cancel task. State conflict.")
    except Exception as e:
        db.rollback()
        logger.error(f"Database error cancelling task {task_id}: {str(e)}")
        raise error_con_codigo(503, "operacion_bd_fallida", detail="Database operation failed")
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
        raise error_con_codigo(404, "no_encontrado", detail="Tarea no encontrada", que="tarea")

    if current_user.role != UserRole.admin:
        project = db.query(Project).filter(Project.id == task.project_id).first()
        is_project_pm = project and project.pm_id == current_user.id
        is_task_participant = (task.assignee_id == current_user.id or task.reporter_id == current_user.id)
        if not is_project_pm and not is_task_participant:
            raise error_con_codigo(403, "sin_acceso_tarea")

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
        raise error_con_codigo(409, "conflicto_concurrente", detail="Cannot add comment. Conflict.")
    except Exception as e:
        db.rollback()
        logger.error(f"Database error adding comment to task {task_id}: {str(e)}")
        raise error_con_codigo(503, "operacion_bd_fallida", detail="Database operation failed")
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
        except ErrorDeDominio:
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
        raise error_con_codigo(409, "conflicto_concurrente", detail="Constraint violation in bulk date update.")
    except Exception as e:
        db.rollback()
        logger.error(f"Database error in bulk_update_dates: {str(e)}")
        raise error_con_codigo(503, "operacion_bd_fallida", detail="Database operation failed")

    # Rev. 173: mover barras en el Gantt recalcula el camino crítico de cada proyecto tocado.
    from app.services.planificador.servicio import recalcular_si_procede
    ids = [c.get("id") for c in updates if c.get("id")]
    for (proyecto,) in (db.query(Task.project_id).filter(Task.id.in_(ids)).distinct().all() if ids else []):
        recalcular_si_procede(db, proyecto)

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


def refresh_profile_bg(background_tasks: "ProgramadorDeTareas", db: "Session", user_id: str) -> None:
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

def _dependencia_dict(d: TaskDependency) -> dict:
    return {
        "id": d.id,
        "predecessor_id": d.predecessor_id,
        "successor_id": d.successor_id,
        "dependency_type": getattr(d.dependency_type, "value", d.dependency_type),
        "lag_days": d.lag_days or 0,
        "link_type": d.link_type or "schedule",
        "note": d.note,
    }


def list_task_dependencies(db: Session, project_id: str, user=None) -> list:
    """Vínculos activos de un proyecto (los que planifican y los informativos).

    Rev. 173: es la única lista de dependencias; la de `/task-dependencies`
    (tabla `task_dependency_meta`) se migró aquí y se retiró.
    """
    if user is not None:
        from app.services.planificador.servicio import proyecto_visible
        proyecto_visible(db, user, project_id)
    q = (
        db.query(TaskDependency)
        .join(Task, TaskDependency.predecessor_id == Task.id)
        .filter(Task.project_id == project_id)
        .filter(TaskDependency.is_active == True)
    )
    return [_dependencia_dict(d) for d in q.all()]


def _cierra_un_ciclo(db: Session, predecessor_id: str, successor_id: str) -> bool:
    """¿Ya se llega de `successor_id` a `predecessor_id` por dependencias que planifican?"""
    pendientes, vistos = [successor_id], set()
    while pendientes:
        actual = pendientes.pop()
        if actual == predecessor_id:
            return True
        if actual in vistos:
            continue
        vistos.add(actual)
        pendientes += [s for (s,) in db.query(TaskDependency.successor_id).filter(
            TaskDependency.predecessor_id == actual, TaskDependency.is_active.is_(True),
            TaskDependency.link_type == "schedule").all()]
    return False


#: Tipos que llegan con nombre de Jira (la página de dependencias y el import):
#: «bloquea» es FS, «bloqueada por» es FS al revés y el resto son vínculos
#: informativos que no planifican.
_TIPOS_INFORMATIVOS = ("relates_to", "duplicates", "cloned_from")


def _normalizar_tipo(dependency_type, link_type, predecessor_id, successor_id):
    from app.models.bookings import TIPOS_DE_VINCULO_DE_TAREA
    tipo = getattr(dependency_type, "value", dependency_type) or "FS"
    vinculo = link_type or "schedule"
    if tipo == "blocks":
        tipo = "FS"
    elif tipo == "blocked_by":
        tipo, predecessor_id, successor_id = "FS", successor_id, predecessor_id
    elif tipo in _TIPOS_INFORMATIVOS:
        tipo, vinculo = "FS", tipo
    if vinculo not in TIPOS_DE_VINCULO_DE_TAREA:
        raise error_con_codigo(400, "valor_no_valido", detail=f"Tipo de vínculo no válido: {vinculo}", valor=vinculo)
    try:
        return DependencyType(tipo), vinculo, predecessor_id, successor_id
    except ValueError:
        raise error_con_codigo(400, "tipo_de_dependencia_no_valido", valor=tipo)


def create_task_dependency(
    db: Session,
    predecessor_id: str,
    successor_id: str,
    dependency_type: str,
    lag_days: int,
    created_by: str,
    link_type: Optional[str] = None,
    note: Optional[str] = None,
) -> dict:
    """
    Create a dependency between two tasks.
    Raises 400 on self-reference or cycle, 404 if a task is missing, 409 if it already exists.
    """
    dependency_type, link_type, predecessor_id, successor_id = _normalizar_tipo(
        dependency_type, link_type, predecessor_id, successor_id)
    if predecessor_id == successor_id:
        raise error_con_codigo(400, "tarea_depende_de_si_misma")
    tareas = {t.id: t for t in db.query(Task).filter(Task.id.in_([predecessor_id, successor_id])).all()}
    if len(tareas) != 2:
        raise error_con_codigo(404, "no_encontrado", detail="Tarea no encontrada", que="tarea")
    if link_type == "schedule" and tareas[predecessor_id].project_id != tareas[successor_id].project_id:
        raise error_con_codigo(400, "dependencia_mismo_proyecto")
    if link_type == "schedule" and _cierra_un_ciclo(db, predecessor_id, successor_id):
        raise error_con_codigo(400, "dependencia_ciclo")
    existing = (
        db.query(TaskDependency)
        .filter(
            TaskDependency.predecessor_id == predecessor_id,
            TaskDependency.successor_id == successor_id,
        ).first()
    )
    if existing and existing.is_active:
        raise error_con_codigo(409, "dependencia_ya_existe", detail="La dependencia ya existe")
    if existing:
        dep = existing
        dep.is_active = True
        dep.dependency_type = dependency_type
        dep.lag_days = lag_days
        dep.link_type = link_type
        dep.note = note
    else:
        dep = TaskDependency(
            organization_id=getattr(tareas[successor_id], "organization_id", None),
            predecessor_id=predecessor_id,
            successor_id=successor_id,
            dependency_type=dependency_type,
            lag_days=lag_days,
            link_type=link_type,
            note=note,
            created_by=created_by,
        )
        db.add(dep)
    db.commit()
    db.refresh(dep)
    if link_type == "schedule":
        from app.services.planificador.servicio import recalcular_si_procede
        recalcular_si_procede(db, tareas[successor_id].project_id)
    return _dependencia_dict(dep)


def update_task_dependency(db: Session, dep_id: str, cambios: dict) -> dict:
    """Cambia tipo, desfase, vínculo o nota de una dependencia y recalcula el plan."""
    dep = db.query(TaskDependency).filter(TaskDependency.id == dep_id, TaskDependency.is_active == True).first()
    if not dep:
        raise error_con_codigo(404, "no_encontrado", detail="Dependencia no encontrada", que="dependencia")
    tipo, vinculo, pred, suc = _normalizar_tipo(
        cambios.get("dependency_type") or dep.dependency_type,
        cambios.get("link_type") or dep.link_type, dep.predecessor_id, dep.successor_id)
    if (pred, suc) != (dep.predecessor_id, dep.successor_id):
        raise error_con_codigo(400, "dependencia_no_invertible")
    if vinculo == "schedule" and dep.link_type != "schedule" and _cierra_un_ciclo(db, pred, suc):
        raise error_con_codigo(400, "dependencia_ciclo")
    dep.dependency_type, dep.link_type = tipo, vinculo
    if cambios.get("lag_days") is not None:
        dep.lag_days = int(cambios["lag_days"])
    if "note" in cambios:
        dep.note = cambios["note"]
    db.commit()
    db.refresh(dep)
    from app.services.planificador.servicio import recalcular_si_procede
    recalcular_si_procede(db, db.query(Task.project_id).filter(Task.id == dep.successor_id).scalar())
    return _dependencia_dict(dep)


def delete_task_dependency(db: Session, dep_id: str) -> dict:
    """Delete a task dependency by id. Raises 404 if not found."""
    dep = db.query(TaskDependency).filter(TaskDependency.id == dep_id, TaskDependency.is_active == True).first()
    if not dep:
        raise error_con_codigo(404, "no_encontrado", detail="Dependencia no encontrada", que="dependencia")
    dep.is_active = False
    db.commit()
    from app.services.planificador.servicio import recalcular_si_procede
    recalcular_si_procede(db, db.query(Task.project_id).filter(Task.id == dep.successor_id).scalar())
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
