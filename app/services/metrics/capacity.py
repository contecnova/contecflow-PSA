"""Capacity & Utilization metrics: load_by_week, productivity_by_person."""
from datetime import date, timedelta
from typing import Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.imputation import Imputation
from app.models.user import User
from app.core.config import settings
from ._registro import register_metric


@register_metric("load_by_week")
def metric_load_by_week(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Carga media del equipo por semana (%) = horas imputadas / capacidad total."""
    users_all = db.query(User).filter(User.is_active == True).all()
    total_capacity = sum(u.weekly_capacity_hours or settings.DEFAULT_WEEKLY_CAPACITY_HOURS for u in users_all)

    imps = db.query(
        Imputation.date,
        func.sum(Imputation.hours).label("h")
    ).filter(
        Imputation.date.between(d_from, d_to)
    )
    if project_ids is not None:
        imps = imps.filter(Imputation.project_id.in_(project_ids))
    if project_id:
        imps = imps.filter(Imputation.project_id == project_id)
    imps = imps.group_by(Imputation.date).all()

    weekly = {}
    for row in imps:
        ws = row.date - timedelta(days=row.date.weekday())
        key = str(ws)
        weekly[key] = weekly.get(key, 0) + row.h

    rows = [
        {
            "label": k[5:],
            "value": round(v / total_capacity * 100, 1) if total_capacity > 0 else 0,
            "hours": round(v, 1)
        }
        for k, v in sorted(weekly.items())
    ]
    return rows, {}


@register_metric("productivity_by_person")
def metric_productivity_by_person(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Productividad por persona: horas reales vs capacidad basada en horario."""
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
            parts = (r.full_name or "").split()
            short_name = (parts[0] + " " + (parts[1][:1] if len(parts) > 1 else "")).strip() if parts else ""
            rows.append({
                "label": short_name,
                "capacity": round(capacity, 1),
                "actual": round(actual, 1),
                "pct": round(actual / capacity * 100, 1) if capacity > 0 else 0,
                "value": round(actual, 1),
            })

    rows.sort(key=lambda x: x["actual"], reverse=True)
    return rows[:top_n], {}
