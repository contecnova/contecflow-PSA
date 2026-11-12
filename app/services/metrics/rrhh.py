"""RRHH metrics: absences_by_type, absences_by_person, absences_by_month."""
from datetime import date
from typing import Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.resources import Absence, AbsenceStatus
from app.models.user import User
from ._registro import register_metric


def _month_label(d) -> str:
    """Format date to "Ene 2024" format."""
    months = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
    if hasattr(d, "month"):
        return f"{months[d.month - 1]} {d.year}"
    return str(d)


TYPE_LABELS = {
    "vacation": "Vacaciones",
    "sick": "Baja médica",
    "personal": "Personal",
    "training": "Formación",
    "maternity": "Maternidad",
    "paternity": "Paternidad",
    "other": "Otro"
}


@register_metric("absences_by_type")
def metric_absences_by_type(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Días de ausencia aprobada por tipo."""
    q = db.query(
        Absence.type,
        func.sum(Absence.working_days).label("days")
    ).filter(
        Absence.status == AbsenceStatus.approved,
        Absence.start_date.between(d_from, d_to)
    ).group_by(Absence.type)

    rows = [
        {"label": TYPE_LABELS.get(r.type, r.type), "value": round(r.days or 0, 1)}
        for r in q.all()
    ]
    return rows, {}


@register_metric("absences_by_person")
def metric_absences_by_person(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Días de ausencia por empleado."""
    q = db.query(
        User.full_name,
        func.sum(Absence.working_days).label("days")
    ).join(
        Absence,
        Absence.user_id == User.id
    ).filter(
        Absence.status == AbsenceStatus.approved,
        Absence.start_date.between(d_from, d_to)
    ).group_by(
        User.full_name
    ).order_by(
        func.sum(Absence.working_days).desc()
    ).limit(top_n)

    rows = [
        {"label": r.full_name, "value": round(r.days or 0, 1)}
        for r in q.all()
    ]
    return rows, {}


@register_metric("absences_by_month")
def metric_absences_by_month(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Días de ausencia acumulados por mes."""
    monthly = {}
    for a in db.query(Absence).filter(
        Absence.status == AbsenceStatus.approved,
        Absence.start_date.between(d_from, d_to)
    ).all():
        key = a.start_date.strftime("%Y-%m")
        monthly[key] = monthly.get(key, 0) + (a.working_days or 0)

    rows = [
        {"label": _month_label(date.fromisoformat(k + "-01")), "value": round(v, 1)}
        for k, v in sorted(monthly.items())
    ]
    return rows, {}
