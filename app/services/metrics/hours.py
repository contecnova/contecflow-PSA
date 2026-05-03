"""
Horas metrics: hours_by_project, hours_by_week, hours_by_month, hours_by_department,
hours_billable_vs_internal, hours_heatmap.
"""
from datetime import date, timedelta
from typing import Optional
from sqlalchemy import func, case
from sqlalchemy.orm import Session

from app.models.imputation import Imputation
from app.models.project import Project
from app.models.user import User
from . import register_metric


def _is_sqlite(db: Session) -> bool:
    bind = db.get_bind()
    return bool(bind and bind.dialect.name == "sqlite")


def _week_bucket_expr(db: Session):
    if _is_sqlite(db):
        return func.strftime('%Y-%W', Imputation.date)
    return func.date_trunc('week', Imputation.date)


def _month_bucket_expr(db: Session):
    if _is_sqlite(db):
        return func.strftime('%Y-%m-01', Imputation.date)
    return func.date_trunc('month', Imputation.date)


def _month_label(d) -> str:
    """Format date to "Ene 2024" format."""
    months = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
    if hasattr(d, "month"):
        return f"{months[d.month - 1]} {d.year}"
    return str(d)


@register_metric("hours_by_project")
def metric_hours_by_project(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Horas totales por proyecto en rango de fechas."""
    q = db.query(
        Project.name.label("name"),
        Project.code.label("code"),
        func.sum(Imputation.hours).label("value")
    ).join(
        Imputation,
        Imputation.project_id == Project.id,
    ).filter(Imputation.date.between(d_from, d_to))

    if project_ids is not None:
        q = q.filter(Project.id.in_(project_ids))

    if user_id:
        q = q.filter(Imputation.user_id == user_id)

    rows = [
        {"label": f"{r.code} {r.name}", "value": round(r.value or 0, 1)}
        for r in q.group_by(Project.name, Project.code)
        .order_by(func.sum(Imputation.hours).desc())
        .limit(top_n)
        .all()
    ]
    return rows, {}


@register_metric("hours_by_week")
def metric_hours_by_week(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Evolución semanal de horas imputadas."""
    week_bucket = _week_bucket_expr(db)
    q = db.query(
        week_bucket.label('week_start'),
        func.sum(Imputation.hours).label('value')
    ).filter(Imputation.date.between(d_from, d_to))
    if project_ids is not None:
        q = q.filter(Imputation.project_id.in_(project_ids))
    if project_id:
        q = q.filter(Imputation.project_id == project_id)
    if user_id:
        q = q.filter(Imputation.user_id == user_id)
    q = q.group_by(week_bucket).order_by(week_bucket)
    rows = [
        {"label": str(r.week_start)[5:10], "full_label": str(r.week_start), "value": round(r.value or 0, 1)}
        for r in q.all()
    ]
    return rows, {}


@register_metric("hours_by_month")
def metric_hours_by_month(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Evolución mensual de horas imputadas."""
    month_bucket = _month_bucket_expr(db)
    q = db.query(
        month_bucket.label('month_start'),
        func.sum(Imputation.hours).label('value')
    ).filter(Imputation.date.between(d_from, d_to))
    if project_ids is not None:
        q = q.filter(Imputation.project_id.in_(project_ids))
    if project_id:
        q = q.filter(Imputation.project_id == project_id)
    if user_id:
        q = q.filter(Imputation.user_id == user_id)
    q = q.group_by(month_bucket).order_by(month_bucket)
    rows = [
        {"label": str(r.month_start)[5:7] + "/" + str(r.month_start)[:4], "full_label": str(r.month_start), "value": round(r.value or 0, 1)}
        for r in q.all()
    ]
    return rows, {}


@register_metric("hours_by_department")
def metric_hours_by_department(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Horas totales agrupadas por departamento."""
    q = db.query(
        User.department.label("dept"),
        func.sum(Imputation.hours).label("value")
    ).join(
        Imputation,
        Imputation.user_id == User.id,
    ).filter(
        Imputation.date.between(d_from, d_to),
        User.department.isnot(None)
    )
    if project_ids is not None:
        q = q.filter(Imputation.project_id.in_(project_ids))
    if project_id:
        q = q.filter(Imputation.project_id == project_id)

    rows = [
        {"label": r.dept or "Sin depto", "value": round(r.value or 0, 1)}
        for r in q.group_by(User.department)
        .order_by(func.sum(Imputation.hours).desc())
        .all()
    ]
    return rows, {}


@register_metric("hours_billable_vs_internal")
def metric_hours_billable_vs_internal(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Horas facturables vs internas por persona."""
    q = db.query(
        User.full_name.label("name"),
        func.sum(case((Imputation.is_billable == True, Imputation.hours), else_=0)).label("billable"),
        func.sum(case((Imputation.is_billable == False, Imputation.hours), else_=0)).label("internal"),
    ).join(
        Imputation,
        Imputation.user_id == User.id
    ).filter(Imputation.date.between(d_from, d_to))

    if project_ids is not None:
        q = q.filter(Imputation.project_id.in_(project_ids))

    if project_id:
        q = q.filter(Imputation.project_id == project_id)

    rows = [
        {
            "label": r.name,
            "billable": round(r.billable or 0, 1),
            "internal": round(r.internal or 0, 1),
            "value": round((r.billable or 0) + (r.internal or 0), 1)
        }
        for r in q.group_by(User.full_name)
        .order_by(func.sum(Imputation.hours).desc())
        .limit(top_n)
        .all()
    ]
    return rows, {}


@register_metric("hours_by_person")
def metric_hours_by_person(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Horas totales imputadas por persona en rango de fechas."""
    q = db.query(
        User.full_name.label("name"),
        func.sum(Imputation.hours).label("value")
    ).join(
        Imputation,
        Imputation.user_id == User.id,
    ).filter(Imputation.date.between(d_from, d_to))

    if project_ids is not None:
        q = q.filter(Imputation.project_id.in_(project_ids))
    if project_id:
        q = q.filter(Imputation.project_id == project_id)

    rows = [
        {"label": r.name, "value": round(r.value or 0, 1)}
        for r in q.group_by(User.full_name)
        .order_by(func.sum(Imputation.hours).desc())
        .limit(top_n)
        .all()
    ]
    return rows, {}


@register_metric("hours_heatmap")
def metric_hours_heatmap(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Heatmap: horas person × semana."""
    imps = db.query(
        User.full_name,
        Imputation.date,
        func.sum(Imputation.hours).label("h")
    ).join(
        User,
        User.id == Imputation.user_id
    ).filter(Imputation.date.between(d_from, d_to))

    if project_ids is not None:
        imps = imps.filter(Imputation.project_id.in_(project_ids))

    if project_id:
        imps = imps.filter(Imputation.project_id == project_id)

    imps = imps.group_by(User.full_name, Imputation.date).all()

    heatmap = {}
    weeks = set()
    for row in imps:
        ws = str(row.date - timedelta(days=row.date.weekday()))
        weeks.add(ws)
        key = (row.full_name, ws)
        heatmap[key] = heatmap.get(key, 0) + row.h

    week_list = sorted(weeks)[-16:]
    persons = list({k[0] for k in heatmap.keys()})[:top_n]

    rows = []
    for p in persons:
        row_data = {"label": p}
        for w in week_list:
            row_data[w[5:]] = round(heatmap.get((p, w), 0), 1)
        rows.append(row_data)

    meta_patch = {"weeks": [w[5:] for w in week_list], "persons": persons}
    return rows, meta_patch
