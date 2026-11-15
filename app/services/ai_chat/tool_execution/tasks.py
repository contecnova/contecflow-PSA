"""Herramientas de tareas: vencidas, creación y actualización."""
from __future__ import annotations

from app.models.task import Task
from app.services.ai_chat.tool_execution.politica import buscar_persona


def _get_overdue_tasks(tool_input, db, user, now, is_financial_role):
    # Segunda auditoría 2026-11: el listado de `GET /tasks` (empleado y externo,
    # solo las suyas), con su filtro de vencidas.
    from app.services.tasks.queries import build_task_list_query
    q = build_task_list_query(db, user, project_id=tool_input.get("project_id") or None, overdue_only=True)
    tasks = q.order_by(Task.due_date).limit(tool_input.get("limit", 20)).all()
    return {"overdue_tasks": [{
        "id": t.id, "title": t.title, "status": t.status,
        "due_date": str(t.due_date)[:10] if t.due_date else None,
        "priority": t.priority, "project_id": t.project_id,
        "project_name": t.project.name if t.project else "?",
        "days_overdue": (now.date() - t.due_date).days if t.due_date else None,
    } for t in tasks]}


def _asignado(tool_input, db, user):
    nombre = tool_input.get("assignee_name")
    return buscar_persona(db, user, nombre) if nombre else None


def _create_task(tool_input, db, user, now, is_financial_role):
    # Como `POST /tasks`: ABAC `task/create` y el mismo servicio, que valida el
    # proyecto (`project_for_user`) y deja fuera a empleado y externo.
    from app.core.abac_enforce import enforce_abac
    from app.schemas import TaskCreate
    from app.services.task_service import create_task_record
    enforce_abac(db, user, "task", action="create")
    assignee = _asignado(tool_input, db, user)
    datos = {k: tool_input[k] for k in ("title", "priority", "estimated_hours", "due_date") if tool_input.get(k)}
    task = create_task_record(db, TaskCreate(project_id=tool_input.get("project_id", ""),
                                             assignee_id=assignee.id if assignee else None, **datos), user)
    return {"ok": True, "task_id": task.id, "code": task.code, "title": task.title,
            "assignee": assignee.full_name if assignee else None}


def _update_task(tool_input, db, user, now, is_financial_role):
    # Como `PATCH /tasks/{id}`: ABAC `task/update` y `update_task_record`, que
    # autoriza (admin, su PM o su asignado) y valida la transición.
    from app.core.abac_enforce import enforce_abac
    from app.schemas import TaskUpdate
    from app.services.task_service import update_task_record
    enforce_abac(db, user, "task", tool_input["task_id"], action="update")
    datos = {k: tool_input[k] for k in ("status", "priority", "due_date") if tool_input.get(k)}
    assignee = _asignado(tool_input, db, user)
    if assignee:
        datos["assignee_id"] = assignee.id
    task, _ = update_task_record(db, tool_input["task_id"], TaskUpdate(**datos), user)
    return {"ok": True, "task_id": task.id, "title": task.title,
            "status": task.status, "priority": task.priority}


HANDLERS = {
    "get_overdue_tasks": _get_overdue_tasks,
    "create_task": _create_task,
    "update_task": _update_task,
}
