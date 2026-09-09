"""
tasks/core.py — La política de transiciones de estado de una tarea.

Exports:
    _TASK_VALID_TRANSITIONS
    validate_task_transition
    apply_status_side_effects
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException

from app.models.task import TaskStatus

# ── Transition policy ─────────────────────────────────────────────────────────
# Auditoría 2026-08 (hallazgo 18). Aquí había un comentario que decía «toda
# transición entre estados está permitida», y **la tabla que tiene justo debajo
# prohíbe la mitad**: `cancelled` es terminal, `backlog` sólo va a `todo` o
# `cancelled`, y `todo` no puede saltar a `in_review`. El comentario describía
# una política que este código no implementa; se corrige en lugar de borrarlo,
# porque lo que sí es verdad merece quedar escrito:
#
#   · la máquina de estados **es** restrictiva, y `validate_task_transition`
#     devuelve 400 con los dos estados en el mensaje;
#   · la trazabilidad va por `TaskMovementLog` — quién, cuándo, desde, hasta y
#     un `move_reason` opcional — y eso es independiente de la tabla;
#   · `todo → done` **sí** está permitido: una tarea pequeña se marca hecha sin
#     pasar por `in_progress`, que es el gesto normal en un tablero. Nadie lee
#     `Task.started_at` más que el propio asignador de sellos, así que saltarse
#     `in_progress` no deja ningún cálculo de duración a medias.
#
# Ese último punto es la razón de que esta tabla haya cambiado: **existía dos
# veces y las dos copias no decían lo mismo**. La de `task_service.py` —la que
# de verdad se ejecutaba, porque es la que importa el endpoint— permitía
# `todo → done`; ésta lo prohibía. Se unifica en la viva: cambiar el
# comportamiento de un tablero en producción es una decisión de producto, no un
# arreglo de auditoría.

_TASK_VALID_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.backlog:     {TaskStatus.todo, TaskStatus.cancelled},
    TaskStatus.todo:        {TaskStatus.in_progress, TaskStatus.done, TaskStatus.backlog,
                              TaskStatus.cancelled},
    TaskStatus.in_progress: {TaskStatus.in_review, TaskStatus.todo, TaskStatus.done,
                              TaskStatus.blocked, TaskStatus.cancelled},
    TaskStatus.in_review:   {TaskStatus.done, TaskStatus.in_progress, TaskStatus.cancelled},
    TaskStatus.done:        {TaskStatus.in_progress},  # reopen
    TaskStatus.blocked:     {TaskStatus.in_progress, TaskStatus.todo, TaskStatus.cancelled},
    TaskStatus.cancelled:   set(),  # terminal
}


def validate_task_transition(current_status: TaskStatus, new_status: TaskStatus) -> None:
    """Raise 400 if the transition is not permitted by _TASK_VALID_TRANSITIONS."""
    allowed = _TASK_VALID_TRANSITIONS.get(current_status, set())
    if new_status not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Transición inválida: {current_status.value} → {new_status.value}.",
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
            getattr(task, '_sa_instance_state', None)
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


# ── TaskService ───────────────────────────────────────────────────────────────
# Auditoría 2026-08 (hallazgo 18). Aquí vivía `class TaskService(ServiceBase)`:
# 387 líneas, once métodos, y **ni un solo sitio de llamada** en todo el
# repositorio. Era el dominio de tareas entero escrito por segunda vez.
#
# Se comparó método a método contra las funciones procedurales de
# `task_service.py` (que son las que ejecuta `endpoints/tasks.py`),
# normalizando `self.db`→`db` y `self.current_user`→`current_user`. El
# resultado, en las once parejas, fue el mismo: **la versión viva es un
# superconjunto estricto**. Lo que la clase muerta NO tenía:
#
#   · `.get` y `.add_comment` → sin el acotado por `Project.organization_id`,
#     así que buscaban la tarea por id **en todos los tenants**;
#   · `.cancel` → igual, y además sin el 400 de «ya está cancelada»;
#   · `.bulk_update_dates` → sin la llamada a `enforce_abac` por tarea;
#   · `.create_dependency` → sin reactivar una dependencia borrada en lógico
#     (daba 409 y dejaba al usuario sin salida);
#   · `.delete_dependency` → hacía `db.delete(dep)` **físico**, cuando la
#     convención de la tabla es `is_active`.
#
# O sea: la copia muerta no era una alternativa, era la versión de antes de los
# arreglos de tenant (#62) y de ABAC. Y no es una curiosidad: mantener dos
# implementaciones del mismo dominio es exactamente lo que produjo el hueco de
# `bulk_update_tasks` que se documenta en `task_service.py`. Se borra.
