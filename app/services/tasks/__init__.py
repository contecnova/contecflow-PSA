"""
app/services/tasks — Task service package.

Re-exports everything for backward compatibility with code that does:
    from app.services.tasks import X
"""
from app.services.tasks.core import (
    TaskService,
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
)

__all__ = [
    # Core
    "TaskService",
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
]
