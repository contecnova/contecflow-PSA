"""
app/services/tasks — Task service package.

Re-exports everything for backward compatibility with code that does:
    from app.services.tasks import X
"""
# Auditoría 2026-08 (hallazgo 18): aquí se reexportaba también `TaskService`,
# la implementación de clase del dominio de tareas. Estaba muerta y era una
# copia vieja de la procedural — el porqué está escrito en `tasks/core.py`.
from app.services.tasks.core import (
    validate_task_transition,
    apply_status_side_effects,
    _TASK_VALID_TRANSITIONS,
)
from app.services.tasks.bulk import bulk_update_tasks
from app.services.tasks.scheduling import cascade_reschedule
from app.services.tasks.queries import (
    get_task_by_id,
    get_tasks_for_project,
    get_project_member_ids,
    task_query_for_user,
    project_for_user,
    build_task_list_query,
)

__all__ = [
    # Core
    "validate_task_transition",
    "apply_status_side_effects",
    "_TASK_VALID_TRANSITIONS",
    # Bulk
    "bulk_update_tasks",
    # Scheduling
    "cascade_reschedule",
    # Queries
    "get_task_by_id",
    "get_tasks_for_project",
    "get_project_member_ids",
    "task_query_for_user",
    "project_for_user",
    "build_task_list_query",
]
