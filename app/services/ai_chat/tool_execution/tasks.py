"""Herramientas de tareas: vencidas, creación y actualización."""
from __future__ import annotations

import uuid as _uuid
from datetime import datetime

from app.models.project import Project
from app.models.task import Task
from app.models.user import User


def _get_overdue_tasks(tool_input, db, user, now, is_financial_role):
    q = db.query(Task).filter(Task.status != "done", Task.due_date < now.date())
    if tool_input.get("project_id"):
        q = q.filter(Task.project_id == tool_input["project_id"])
    tasks = q.order_by(Task.due_date).limit(tool_input.get("limit", 20)).all()
    proj_ids = {t.project_id for t in tasks}
    proj_map = {p.id: p for p in db.query(Project).filter(Project.id.in_(proj_ids)).all()}
    return {"overdue_tasks": [{
        "id": t.id, "title": t.title, "status": t.status,
        "due_date": str(t.due_date)[:10] if t.due_date else None,
        "priority": t.priority, "project_id": t.project_id,
        "project_name": proj_map[t.project_id].name if t.project_id in proj_map else "?",
        "days_overdue": (now.date() - t.due_date).days if t.due_date else None,
    } for t in tasks]}


def _create_task(tool_input, db, user, now, is_financial_role):
    project = db.query(Project).filter(Project.id == tool_input.get("project_id", "")).first()
    if not project: return {"error": "Proyecto no encontrado"}
    assignee = None
    if tool_input.get("assignee_name"):
        assignee = db.query(User).filter(
            User.full_name.ilike(f"%{tool_input['assignee_name']}%")
        ).first()
    task_code = "TSK-" + str(_uuid.uuid4())[:8].upper()
    task = Task(
        project_id=project.id, code=task_code, title=tool_input["title"],
        status="todo", priority=tool_input.get("priority", "medium"),
        estimated_hours=tool_input.get("estimated_hours"),
        assignee_id=assignee.id if assignee else None,
        created_by=user.id,
    )
    if tool_input.get("due_date"):
        task.due_date = datetime.strptime(tool_input["due_date"], "%Y-%m-%d").date()
    db.add(task); db.flush()
    return {"ok": True, "task_id": task.id, "code": task_code, "title": task.title,
            "assignee": assignee.full_name if assignee else None}


def _update_task(tool_input, db, user, now, is_financial_role):
    task = db.query(Task).filter(Task.id == tool_input["task_id"]).first()
    if not task: return {"error": "Tarea no encontrada"}
    if tool_input.get("status"): task.status = tool_input["status"]
    if tool_input.get("priority"): task.priority = tool_input["priority"]
    if tool_input.get("due_date"):
        task.due_date = datetime.strptime(tool_input["due_date"], "%Y-%m-%d").date()
    if tool_input.get("assignee_name"):
        u = db.query(User).filter(User.full_name.ilike(f"%{tool_input['assignee_name']}%")).first()
        if u: task.assignee_id = u.id
    db.flush()
    return {"ok": True, "task_id": task.id, "title": task.title,
            "status": task.status, "priority": task.priority}


HANDLERS = {
    "get_overdue_tasks": _get_overdue_tasks,
    "create_task": _create_task,
    "update_task": _update_task,
}
