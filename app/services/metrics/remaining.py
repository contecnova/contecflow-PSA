"""Remaining metrics: sprints, semantic, load profiles, etc."""
from datetime import date
from typing import Optional
from sqlalchemy import func, case
from sqlalchemy.orm import Session

from . import register_metric
from app.core.config import settings
from app.models.imputation import Imputation
from app.models.user import User
from datetime import timedelta


@register_metric("sprint_velocity")
def metric_sprint_velocity(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Velocidad de sprint: story points completados por sprint."""
    try:
        from app.models.sprints import Sprint, SprintTask
        from app.models.task import Task

        sprints_q = db.query(Sprint)
        if project_ids:
            sprints_q = sprints_q.filter(Sprint.project_id.in_(project_ids))
        if project_id:
            sprints_q = sprints_q.filter(Sprint.project_id == project_id)

        sprints = sprints_q.order_by(Sprint.start_date).limit(20).all()
        sprint_ids = [sp.id for sp in sprints]
        sprint_map = {sp.id: sp for sp in sprints}

        # Query all points per sprint in batch
        pts = db.query(
            SprintTask.sprint_id,
            func.sum(case([(Task.status == "done", Task.story_points)], else_=0)).label("done_pts"),
            func.sum(Task.story_points).label("total_pts")
        ).join(Task, SprintTask.task_id == Task.id)
        if sprint_ids:
            pts = pts.filter(SprintTask.sprint_id.in_(sprint_ids))
        pts = pts.group_by(SprintTask.sprint_id).all()
        pts_map = {r[0]: (r[1] or 0, r[2] or 0) for r in pts}

        rows = []
        for sp in sprints:
            done_pts, total_pts = pts_map.get(sp.id, (0, 0))
            rows.append({
                "label": sp.name[:20],
                "completed": done_pts,
                "planned": total_pts,
                "value": done_pts
            })
    except (ImportError, Exception):
        rows = []

    return rows, {}


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
    """Tasa de completitud de sprint."""
    try:
        from app.models.sprints import Sprint, SprintTask
        from app.models.task import Task

        sprints_q = db.query(Sprint)
        if project_ids:
            sprints_q = sprints_q.filter(Sprint.project_id.in_(project_ids))
        if project_id:
            sprints_q = sprints_q.filter(Sprint.project_id == project_id)

        sprints = sprints_q.order_by(Sprint.start_date).limit(20).all()
        sprint_ids = [sp.id for sp in sprints]
        sprint_map = {sp.id: sp for sp in sprints}

        pts = db.query(
            SprintTask.sprint_id,
            func.sum(case([(Task.status == "done", Task.story_points)], else_=0)).label("done_pts"),
            func.sum(Task.story_points).label("total_pts")
        ).join(Task, SprintTask.task_id == Task.id)
        if sprint_ids:
            pts = pts.filter(SprintTask.sprint_id.in_(sprint_ids))
        pts = pts.group_by(SprintTask.sprint_id).all()
        pts_map = {r[0]: (r[1] or 0, r[2] or 0) for r in pts}

        rows = []
        for sp in sprints:
            done_pts, total_pts = pts_map.get(sp.id, (0, 0))
            pct = round(done_pts / total_pts * 100, 1) if total_pts > 0 else 0
            rows.append({
                "label": sp.name[:20],
                "value": pct,
                "done": done_pts,
                "total": total_pts
            })
    except (ImportError, Exception):
        rows = []

    return rows, {}


@register_metric("semantic_accuracy_trend")
def metric_semantic_accuracy_trend(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Tendencia de precisión del motor semántico."""
    try:
        from app.models.semantic_engine import SemAssignment

        monthly = {}
        for sa in db.query(SemAssignment).filter(SemAssignment.was_accepted.isnot(None)).all():
            k = str(sa.created_at)[:7] if sa.created_at else "unknown"
            if k not in monthly:
                monthly[k] = {"accepted": 0, "total": 0}
            monthly[k]["total"] += 1
            if sa.was_accepted:
                monthly[k]["accepted"] += 1

        rows = []
        for k in sorted(monthly.keys())[-12:]:
            m = monthly[k]
            pct = round(m["accepted"] / m["total"] * 100, 1) if m["total"] > 0 else 0
            rows.append({
                "label": k,
                "value": pct,
                "accepted": m["accepted"],
                "total": m["total"]
            })
    except (ImportError, Exception):
        rows = []

    return rows, {}


@register_metric("semantic_assignments_by_mode")
def metric_semantic_assignments_by_mode(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Asignaciones semánticas por modo de motor."""
    try:
        from app.models.semantic_engine import SemAssignment

        MODE_LABELS = {
            "semantic": "Semántico",
            "llm": "LLM",
            "hybrid": "Híbrido",
            "expert_cache_exact": "Cache exacto",
            "expert_cache_semantic": "Cache semántico",
            "rules_only": "Solo reglas"
        }

        rows_raw = db.query(
            SemAssignment.engine_mode,
            func.count(SemAssignment.id).label("n")
        ).group_by(SemAssignment.engine_mode).all()

        rows = [
            {"label": MODE_LABELS.get(r.engine_mode or "", r.engine_mode or "Desconocido"), "value": r.n}
            for r in rows_raw if r.engine_mode
        ]
    except (ImportError, Exception):
        rows = []

    return rows, {}


@register_metric("load_by_person")
def metric_load_by_person(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Carga por persona (% sobre su capacidad)."""

    total_days = (d_to - d_from).days + 1
    working_days = sum(1 for i in range(total_days) if (d_from + timedelta(i)).weekday() < 5)

    q = db.query(
        User.id,
        User.full_name,
        User.weekly_capacity_hours,
        func.coalesce(func.sum(Imputation.hours), 0).label("actual"),
    ).outerjoin(
        Imputation,
        (Imputation.user_id == User.id) & Imputation.date.between(d_from, d_to),
    ).filter(User.is_active == True)

    if project_ids is not None:
        q = q.filter((Imputation.project_id.is_(None)) | (Imputation.project_id.in_(project_ids)))
    if project_id:
        q = q.filter((Imputation.project_id.is_(None)) | (Imputation.project_id == project_id))

    if user_id:
        q = q.filter(User.id == user_id)

    rows = []
    for r in q.group_by(User.id, User.full_name, User.weekly_capacity_hours).all():
        capacity = (r.weekly_capacity_hours or settings.DEFAULT_WEEKLY_CAPACITY_HOURS) / 5 * working_days
        actual = float(r.actual or 0)
        if actual > 0 or capacity > 0:
            pct = round(actual / capacity * 100, 1) if capacity > 0 else 0
            rows.append({
                "label": r.full_name or "Desconocido",
                "value": pct,
                "hours": round(actual, 1),
                "capacity": round(capacity, 1)
            })

    rows.sort(key=lambda x: -x["value"])
    return rows[:top_n], {}
