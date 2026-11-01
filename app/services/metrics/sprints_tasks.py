"""Sprint, Task, Epic and Milestone metrics:
sprint_velocity_trend, sprint_completion_rate, tasks_by_status,
tasks_by_priority, tasks_overdue_by_assignee, task_completion_trend,
tasks_by_assignee, epics_by_status, milestones_on_time_rate."""
from datetime import date
from typing import Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from . import register_metric
from ._monthly import agrupar_por_mes, serie_de_cuentas
from app.core import timeutil


@register_metric("sprint_velocity_trend")
def metric_sprint_velocity_trend(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Evolución de la velocidad (story points) por sprint."""
    try:
        from app.models.sprints import Sprint

        q = db.query(Sprint).filter(
            Sprint.status == "completed",
            Sprint.closed_at >= d_from,
            Sprint.closed_at <= d_to,
        )
        if project_id:
            q = q.filter(Sprint.project_id == project_id)
        elif project_ids:
            q = q.filter(Sprint.project_id.in_(project_ids))
        q = q.order_by(Sprint.closed_at).limit(top_n)

        rows = []
        for s in q.all():
            rows.append({
                "label": s.name or f"Sprint {s.number}",
                "value": s.velocity or s.completed_points or 0,
                "planned": s.planned_points or 0,
                "completed": s.completed_points or 0,
            })
    except Exception:
        rows = []
    return rows, {"y_label": "Story Points"}


@register_metric("sprint_completion_rate")
def metric_sprint_completion_rate(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Tasa de completado (completed/planned %) por sprint."""
    try:
        from app.models.sprints import Sprint

        q = db.query(Sprint).filter(
            Sprint.status == "completed",
            Sprint.closed_at >= d_from,
            Sprint.closed_at <= d_to,
        )
        if project_id:
            q = q.filter(Sprint.project_id == project_id)
        elif project_ids:
            q = q.filter(Sprint.project_id.in_(project_ids))
        q = q.order_by(Sprint.closed_at).limit(top_n)

        rows = []
        for s in q.all():
            planned = s.planned_points or 0
            completed = s.completed_points or 0
            rate = round(completed / planned * 100, 1) if planned else 0
            rows.append({
                "label": s.name or f"Sprint {s.number}",
                "value": rate,
                "planned": planned,
                "completed": completed,
            })
    except Exception:
        rows = []
    return rows, {"y_label": "Completado (%)"}


@register_metric("tasks_by_status")
def metric_tasks_by_status(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Distribución de tareas por estado."""
    try:
        from app.models.task import Task

        q = db.query(Task.status, func.count(Task.id).label("cnt"))
        if project_id:
            q = q.filter(Task.project_id == project_id)
        elif project_ids:
            q = q.filter(Task.project_id.in_(project_ids))
        q = q.group_by(Task.status).order_by(func.count(Task.id).desc())

        rows = [{"label": r.status or "Sin estado", "value": r.cnt} for r in q.all()]
    except Exception:
        rows = []
    return rows, {}


@register_metric("tasks_by_priority")
def metric_tasks_by_priority(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Distribución de tareas por prioridad."""
    try:
        from app.models.task import Task

        q = db.query(Task.priority, func.count(Task.id).label("cnt"))
        if project_id:
            q = q.filter(Task.project_id == project_id)
        elif project_ids:
            q = q.filter(Task.project_id.in_(project_ids))
        q = q.group_by(Task.priority).order_by(func.count(Task.id).desc())

        PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        rows = sorted(
            [{"label": r.priority or "Sin prioridad", "value": r.cnt} for r in q.all()],
            key=lambda x: PRIORITY_ORDER.get(x["label"], 99)
        )
    except Exception:
        rows = []
    return rows, {}


@register_metric("tasks_overdue_by_assignee")
def metric_tasks_overdue_by_assignee(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Tareas vencidas (due_date pasada, no completadas) por responsable."""
    try:
        from app.models.task import Task
        from app.models.user import User

        today = timeutil.today()
        q = db.query(Task.assignee_id, func.count(Task.id).label("cnt")).filter(
            Task.due_date < today,
            Task.status.notin_(["done", "cancelled"]),
        )
        if project_id:
            q = q.filter(Task.project_id == project_id)
        elif project_ids:
            q = q.filter(Task.project_id.in_(project_ids))
        q = q.group_by(Task.assignee_id).order_by(func.count(Task.id).desc()).limit(top_n)

        user_ids = [r.assignee_id for r in q.all() if r.assignee_id]
        users_map = {u.id: u.full_name or u.email for u in db.query(User).filter(User.id.in_(user_ids)).all()} if user_ids else {}

        rows = [
            {"label": users_map.get(r.assignee_id, "Sin asignar"), "value": r.cnt}
            for r in q.all()
        ]
    except Exception:
        rows = []
    return rows, {"y_label": "Tareas vencidas"}


@register_metric("task_completion_trend")
def metric_task_completion_trend(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Evolución mensual de tareas completadas."""
    try:
        from app.models.task import Task

        # `completed_at` es DateTime(timezone=True) y guarda UTC: el
        # `extract("month", ...)` anterior agrupaba por mes UTC, asi que una tarea
        # cerrada a las 23:30 del ultimo dia del mes contaba en el mes siguiente.
        q = db.query(Task.completed_at).filter(
            Task.completed_at >= d_from,
            Task.completed_at <= d_to,
            Task.status == "done",
        )
        if project_id:
            q = q.filter(Task.project_id == project_id)
        elif project_ids:
            q = q.filter(Task.project_id.in_(project_ids))

        rows = serie_de_cuentas(agrupar_por_mes(q.all(), lambda r: r[0]))
    except Exception:
        rows = []
    return rows, {"y_label": "Tareas completadas"}


@register_metric("tasks_by_assignee")
def metric_tasks_by_assignee(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Carga actual de trabajo: tareas abiertas por persona."""
    try:
        from app.models.task import Task
        from app.models.user import User

        q = db.query(Task.assignee_id, func.count(Task.id).label("cnt")).filter(
            Task.status.notin_(["done", "cancelled"]),
        )
        if project_id:
            q = q.filter(Task.project_id == project_id)
        elif project_ids:
            q = q.filter(Task.project_id.in_(project_ids))
        q = q.group_by(Task.assignee_id).order_by(func.count(Task.id).desc()).limit(top_n)

        user_ids = [r.assignee_id for r in q.all() if r.assignee_id]
        users_map = {u.id: u.full_name or u.email for u in db.query(User).filter(User.id.in_(user_ids)).all()} if user_ids else {}

        rows = [
            {"label": users_map.get(r.assignee_id, "Sin asignar"), "value": r.cnt}
            for r in q.all()
        ]
    except Exception:
        rows = []
    return rows, {"y_label": "Tareas abiertas"}


@register_metric("epics_by_status")
def metric_epics_by_status(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Distribución de épicas por estado."""
    try:
        from app.models.epics import Epic

        q = db.query(Epic.status, func.count(Epic.id).label("cnt"))
        if project_id:
            q = q.filter(Epic.project_id == project_id)
        elif project_ids:
            q = q.filter(Epic.project_id.in_(project_ids))
        q = q.group_by(Epic.status).order_by(func.count(Epic.id).desc())

        rows = [{"label": r.status or "Sin estado", "value": r.cnt} for r in q.all()]
    except Exception:
        rows = []
    return rows, {}


@register_metric("milestones_on_time_rate")
def metric_milestones_on_time_rate(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Tasa de hitos completados a tiempo vs con retraso."""
    try:
        from app.models.financial import ProjectMilestone

        q = db.query(ProjectMilestone).filter(
            ProjectMilestone.is_completed == True,
            ProjectMilestone.completed_date >= d_from,
            ProjectMilestone.completed_date <= d_to,
        )
        if project_id:
            q = q.filter(ProjectMilestone.project_id == project_id)
        elif project_ids:
            q = q.filter(ProjectMilestone.project_id.in_(project_ids))

        milestones = q.all()
        on_time = sum(1 for m in milestones if m.completed_date and m.due_date and m.completed_date <= m.due_date)
        late = len(milestones) - on_time

        rows = [
            {"label": "A tiempo", "value": on_time},
            {"label": "Con retraso", "value": late},
        ]
    except Exception:
        rows = []
    return rows, {}
