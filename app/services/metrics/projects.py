"""
Projects & Tasks metrics: tasks_by_status, tasks_by_project, projects_by_status,
deliverables_status, tasks_lead_time, tasks_blocked_by_project, tasks_overdue, risks_by_level.
"""
from datetime import date
from typing import Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.task import Task
from app.models.resources import Deliverable
from . import register_metric
from app.core import timeutil


STATUS_TASK_LABELS = {
    "todo": "Por hacer",
    "in_progress": "En curso",
    "in_review": "En revisión",
    "done": "Hecho",
    "blocked": "Bloqueado"
}

STATUS_PROJECT_LABELS = {
    "planning": "Planificación",
    "active": "Activo",
    "paused": "Pausado",
    "closed": "Cerrado",
    "cancelled": "Cancelado"
}

TYPE_PROJECT_LABELS = {
    "development": "Desarrollo",
    "maintenance": "Mantenimiento",
    "rd": "I+D",
    "internal": "Interno",
    "consulting": "Consultoría",
}

STATUS_DELIVERABLE_LABELS = {
    "planned": "Planificado",
    "in_progress": "En curso",
    "in_review": "En revisión",
    "delivered": "Entregado",
    "accepted": "Aceptado",
    "rejected": "Rechazado"
}


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
    """Número de tareas por estado."""
    q = db.query(Task.status, func.count(Task.id).label("count"))
    if project_ids:
        q = q.filter(Task.project_id.in_(project_ids))

    rows = [
        {"label": STATUS_TASK_LABELS.get(r.status, r.status), "value": r.count}
        for r in q.group_by(Task.status).all()
    ]
    return rows, {}


@register_metric("tasks_by_project")
def metric_tasks_by_project(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Número de tareas por proyecto."""
    q = db.query(
        Project.name,
        Project.code,
        func.count(Task.id).label("count")
    ).join(
        Task,
        Task.project_id == Project.id
    )

    if project_ids:
        q = q.filter(Project.id.in_(project_ids))

    q = q.group_by(
        Project.name,
        Project.code
    ).order_by(
        func.count(Task.id).desc()
    ).limit(top_n)

    rows = [
        {"label": r.code, "value": r.count}
        for r in q.all()
    ]
    return rows, {}


@register_metric("projects_by_status")
def metric_projects_by_status(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Distribución de proyectos por estado."""
    q = db.query(Project.status, func.count(Project.id).label("count")).group_by(Project.status)
    if project_ids:
        q = q.filter(Project.id.in_(project_ids))

    rows = [
        {"label": STATUS_PROJECT_LABELS.get(r.status, r.status), "value": r.count}
        for r in q.all()
    ]
    return rows, {}


@register_metric("projects_by_type")
def metric_projects_by_type(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Distribución de proyectos por tipo."""
    q = db.query(Project.project_type, func.count(Project.id).label("count")).group_by(Project.project_type)
    if project_ids:
        q = q.filter(Project.id.in_(project_ids))

    def _key(t):
        return t.value if hasattr(t, "value") else t

    rows = [
        {"label": TYPE_PROJECT_LABELS.get(_key(r.project_type), _key(r.project_type) or "Sin tipo"), "value": r.count}
        for r in q.all()
    ]
    rows.sort(key=lambda x: x["value"], reverse=True)
    return rows, {}


@register_metric("projects_by_client")
def metric_projects_by_client(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Proyectos activos y completados por cliente (revisión 2026-11: estaba en
    el catálogo sin cálculo y salía siempre vacío)."""
    q = db.query(Project.client_name, Project.status, func.count(Project.id).label("n")) \
        .group_by(Project.client_name, Project.status)
    if project_ids:
        q = q.filter(Project.id.in_(project_ids))
    por_cliente: dict[str, dict] = {}
    for r in q.all():
        estado = r.status.value if hasattr(r.status, "value") else str(r.status)
        fila = por_cliente.setdefault(r.client_name or "Sin cliente",
                                      {"label": r.client_name or "Sin cliente", "value": 0, "activos": 0, "completados": 0})
        fila["value"] += r.n
        if estado == "active":
            fila["activos"] += r.n
        elif estado in ("completed", "closed"):
            fila["completados"] += r.n
    rows = sorted(por_cliente.values(), key=lambda x: x["value"], reverse=True)[:top_n]
    return rows, {}


@register_metric("deliverables_status")
def metric_deliverables_status(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Número de entregables por estado."""
    q = db.query(Deliverable.status, func.count(Deliverable.id).label("count")).group_by(Deliverable.status)
    if project_ids:
        q = q.filter(Deliverable.project_id.in_(project_ids))

    rows = [
        {"label": STATUS_DELIVERABLE_LABELS.get(r.status, r.status), "value": r.count}
        for r in q.all()
    ]
    return rows, {}


@register_metric("tasks_lead_time")
def metric_tasks_lead_time(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Lead time promedio de tareas completadas por proyecto."""
    projects_q = db.query(Project).filter(Project.status == "active")
    if project_ids:
        projects_q = projects_q.filter(Project.id.in_(project_ids))
    if project_id:
        projects_q = projects_q.filter(Project.id == project_id)

    rows = []
    for proj in projects_q.all():
        done_tasks = db.query(Task).filter(
            Task.project_id == proj.id,
            Task.status == "done",
            Task.completed_at.isnot(None),
            Task.created_at.isnot(None)
        ).all()

        if done_tasks:
            lead_times = []
            for t in done_tasks:
                try:
                    lead_times.append((t.completed_at - t.created_at).days)
                except Exception:  # noqa: S112
                    continue

            if lead_times:
                rows.append({
                    "label": proj.code or proj.name[:20],
                    "value": round(sum(lead_times) / len(lead_times), 1),
                    "count": len(lead_times)
                })

    rows.sort(key=lambda x: -x["value"])
    return rows, {}


@register_metric("tasks_blocked_by_project")
def metric_tasks_blocked_by_project(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Tareas bloqueadas por proyecto."""
    # Optimized: Single query with GROUP BY
    blocked = db.query(
        Project.name,
        Project.code,
        func.count(Task.id).label("count")
    ).join(
        Task,
        Task.project_id == Project.id
    ).filter(
        Task.status == "blocked"
    )
    if project_ids:
        blocked = blocked.filter(Project.id.in_(project_ids))

    blocked = blocked.group_by(
        Project.name,
        Project.code
    ).order_by(
        func.count(Task.id).desc()
    ).all()

    rows = [
        {"label": r.code or r.name[:20], "value": r.count}
        for r in blocked if r.count > 0
    ]
    return rows, {}


@register_metric("tasks_overdue")
def metric_tasks_overdue(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Tareas retrasadas (vencidas pero no completadas) por proyecto."""
    today = timeutil.today()

    # Optimized: Single query with GROUP BY
    overdue = db.query(
        Project.name,
        Project.code,
        func.count(Task.id).label("count")
    ).join(
        Task,
        Task.project_id == Project.id
    ).filter(
        Task.due_date < today,
        Task.status.notin_(["done", "cancelled"])
    )
    if project_ids:
        overdue = overdue.filter(Project.id.in_(project_ids))

    overdue = overdue.group_by(
        Project.name,
        Project.code
    ).order_by(
        func.count(Task.id).desc()
    ).all()

    rows = [
        {"label": r.code or r.name[:20], "value": r.count}
        for r in overdue if r.count > 0
    ]
    return rows, {}


@register_metric("risks_by_level")
def metric_risks_by_level(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Distribución de riesgos por nivel de severidad."""
    try:
        from app.models.pipeline import Risk
        from app.services.risk_scoring import (
            risk_level as _risk_level, risk_score as _risk_score,
        )

        risks_q = db.query(Risk).filter(Risk.status.notin_(["closed"]))
        if project_ids and hasattr(Risk, "project_id"):
            risks_q = risks_q.filter(Risk.project_id.in_(project_ids))
        risks = risks_q.all()
        levels = {}
        for r in risks:
            lvl = _risk_level(_risk_score(r.probability, r.impact))
            levels[lvl] = levels.get(lvl, 0) + 1

        LEVEL_LABELS = {
            "critical": "Crítico",
            "high": "Alto",
            "medium": "Medio",
            "low": "Bajo"
        }
        rows = [
            {"label": LEVEL_LABELS.get(k, k), "value": v}
            for k, v in sorted(levels.items(), key=lambda x: ["critical", "high", "medium", "low"].index(x[0]))
        ]
    except ImportError:
        rows = []

    return rows, {}
