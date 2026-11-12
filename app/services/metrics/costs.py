"""
Costs metrics: cost_by_project, cost_by_person, cost_by_month, budget_consumption,
cost_vs_budget, margin_by_project, margin_evolution, revenue_by_client.

CRITICAL: margin_by_project debe usar GROUP BY + JOIN para evitar N+1.
"""
from datetime import date
from typing import Optional
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models.imputation import Imputation
from app.models.project import Project
from app.models.user import User
from ._registro import register_metric
from app.models.clients import Client


def _month_label(d) -> str:
    """Format date to "Ene 2024" format."""
    months = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
    if hasattr(d, "month"):
        return f"{months[d.month - 1]} {d.year}"
    return str(d)


@register_metric("cost_by_project")
def metric_cost_by_project(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Coste interno acumulado por proyecto en rango de fechas."""
    q = db.query(
        Project.name,
        Project.code,
        func.sum(Imputation.cost_amount).label("value")
    ).join(
        Imputation,
        Imputation.project_id == Project.id,
    ).filter(Imputation.date.between(d_from, d_to))

    if project_ids is not None:
        q = q.filter(Project.id.in_(project_ids))

    rows = [
        {"label": f"{r.code} {r.name}", "value": round(r.value or 0, 2)}
        for r in q.group_by(Project.name, Project.code)
        .order_by(func.sum(Imputation.cost_amount).desc())
        .limit(top_n)
        .all()
    ]
    return rows, {}


@register_metric("cost_by_person")
def metric_cost_by_person(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Coste acumulado por persona."""
    q = db.query(
        User.full_name,
        func.sum(Imputation.cost_amount).label("value")
    ).join(
        Imputation,
        Imputation.user_id == User.id
    ).filter(Imputation.date.between(d_from, d_to))

    if project_ids is not None:
        q = q.filter(Imputation.project_id.in_(project_ids))

    if project_id:
        q = q.filter(Imputation.project_id == project_id)

    rows = [
        {"label": r.full_name, "value": round(r.value or 0, 2)}
        for r in q.group_by(User.full_name)
        .order_by(func.sum(Imputation.cost_amount).desc())
        .limit(top_n)
        .all()
    ]
    return rows, {}


@register_metric("cost_by_month")
def metric_cost_by_month(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Evolución mensual de costes."""
    q = db.query(
        func.date_trunc('month', Imputation.date).label('month_start'),
        func.sum(Imputation.cost_amount).label('value')
    ).filter(Imputation.date.between(d_from, d_to))

    if project_ids is not None:
        q = q.filter(Imputation.project_id.in_(project_ids))

    if project_id:
        q = q.filter(Imputation.project_id == project_id)

    q = q.group_by(func.date_trunc('month', Imputation.date)).order_by(func.date_trunc('month', Imputation.date))
    rows = [
        {"label": _month_label(r.month_start), "value": round(r.value or 0, 2)}
        for r in q.all()
    ]
    return rows, {}


@register_metric("budget_consumption")
def metric_budget_consumption(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Porcentaje de presupuesto consumido por proyecto."""
    # Optimized: Get all project costs in one query via GROUP BY
    project_costs_q = db.query(
        Imputation.project_id,
        func.sum(Imputation.cost_amount).label("total_cost")
    ).filter(
        Imputation.date.between(d_from, d_to)
    )
    if project_ids is not None:
        project_costs_q = project_costs_q.filter(Imputation.project_id.in_(project_ids))
    project_costs = project_costs_q.group_by(Imputation.project_id).all()

    cost_by_project = {pc.project_id: pc.total_cost or 0 for pc in project_costs}

    projects = db.query(Project).filter(
        Project.budget_amount.isnot(None),
        Project.budget_amount > 0
    )
    if project_ids is not None:
        projects = projects.filter(Project.id.in_(project_ids))
    projects = projects.limit(top_n).all()

    rows = []
    for p in projects:
        cost = cost_by_project.get(p.id, 0)
        pct = round(cost / p.budget_amount * 100, 1) if p.budget_amount > 0 else 0
        rows.append({
            "label": p.code,
            "value": pct,
            "cost": round(cost, 0),
            "budget": p.budget_amount,
            "status": "critical" if pct > 100 else "warning" if pct > 85 else "ok"
        })

    rows.sort(key=lambda x: x["value"], reverse=True)
    return rows, {}


@register_metric("cost_vs_budget")
def metric_cost_vs_budget(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Comparativa coste vs presupuesto."""
    # Optimized: single query with GROUP BY
    project_costs_q = db.query(
        Imputation.project_id,
        func.sum(Imputation.cost_amount).label("total_cost")
    )
    if project_ids is not None:
        project_costs_q = project_costs_q.filter(Imputation.project_id.in_(project_ids))
    project_costs = project_costs_q.group_by(Imputation.project_id).all()

    cost_by_project = {pc.project_id: pc.total_cost or 0 for pc in project_costs}

    projects = db.query(Project).filter(
        Project.budget_amount.isnot(None)
    )
    if project_ids is not None:
        projects = projects.filter(Project.id.in_(project_ids))
    projects = projects.limit(top_n).all()

    rows = []
    for p in projects:
        cost = cost_by_project.get(p.id, 0)
        rows.append({
            "label": p.code,
            "budget": p.budget_amount or 0,
            "cost": round(cost, 0),
            "value": round(cost, 0)
        })

    rows.sort(key=lambda x: x["cost"], reverse=True)
    return rows, {}


@register_metric("margin_by_project")
def metric_margin_by_project(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """
    Margen por proyecto: (Revenue - Cost) / Revenue.
    OPTIMIZED: Single GROUP BY query instead of per-project loop (was N+1).
    """
    # Revenue is estimated from billable imputations using project billing_rate.
    revenue_expr = Imputation.hours * func.coalesce(Project.billing_rate, 0.0)

    revenue_q = db.query(
        Imputation.project_id,
        func.sum(revenue_expr).label("revenue")
    ).join(
        Project,
        Project.id == Imputation.project_id
    ).filter(
        Imputation.date.between(d_from, d_to),
        Project.is_billable.is_(True),
        Project.billing_rate.isnot(None)
    )
    if project_ids is not None:
        revenue_q = revenue_q.filter(Imputation.project_id.in_(project_ids))
    revenue_q = revenue_q.group_by(Imputation.project_id)

    # Cost: Sum of imputation costs (full cost to org)
    cost_q = db.query(
        Imputation.project_id,
        func.sum(Imputation.cost_amount).label("cost")
    ).filter(
        Imputation.date.between(d_from, d_to),
        Imputation.cost_amount.isnot(None)
    )
    if project_ids is not None:
        cost_q = cost_q.filter(Imputation.project_id.in_(project_ids))
    cost_q = cost_q.group_by(Imputation.project_id)

    # Build lookup dicts for O(1) join
    revenue_by_proj = {r.project_id: r.revenue or 0 for r in revenue_q.all()}
    cost_by_proj = {r.project_id: r.cost or 0 for r in cost_q.all()}

    # Join with Project to get names
    projects = db.query(Project).filter(Project.id.in_(list(revenue_by_proj.keys())))
    if project_ids is not None:
        projects = projects.filter(Project.id.in_(project_ids))
    projects = projects.limit(top_n).all()

    rows = []
    for p in projects:
        rev = revenue_by_proj.get(p.id, 0)
        cost = cost_by_proj.get(p.id, 0)
        margin = round((rev - cost) / rev * 100, 1) if rev > 0 else 0
        rows.append({
            "label": f"{p.code}",
            "revenue": round(rev, 0),
            "cost": round(cost, 0),
            "margin": margin,
            "value": margin
        })

    rows.sort(key=lambda x: x["value"], reverse=True)
    return rows, {}


@register_metric("margin_evolution")
def metric_margin_evolution(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Evolución mensual del margen (revenue - cost) / revenue."""
    revenue_expr = case(
        (
            Project.is_billable.is_(True),
            Imputation.hours * func.coalesce(Project.billing_rate, 0.0),
        ),
        else_=0.0,
    )

    monthly_q = db.query(
        func.date_trunc('month', Imputation.date).label('month_start'),
        func.sum(revenue_expr).label('revenue'),
        func.sum(Imputation.cost_amount).label('cost')
    ).join(
        Project,
        Project.id == Imputation.project_id
    ).filter(Imputation.date.between(d_from, d_to))

    if project_ids is not None:
        monthly_q = monthly_q.filter(Imputation.project_id.in_(project_ids))

    monthly_q = monthly_q.group_by(
        func.date_trunc('month', Imputation.date)
    ).order_by(
        func.date_trunc('month', Imputation.date)
    )

    rows = []
    for r in monthly_q.all():
        rev = r.revenue or 0
        cost = r.cost or 0
        margin = round((rev - cost) / rev * 100, 1) if rev > 0 else 0
        rows.append({
            "label": _month_label(r.month_start),
            "revenue": round(rev, 0),
            "cost": round(cost, 0),
            "margin": margin,
            "value": margin
        })

    return rows, {}


@register_metric("revenue_by_client")
def metric_revenue_by_client(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Ingresos facturados por cliente."""
    revenue_expr = Imputation.hours * func.coalesce(Project.billing_rate, 0.0)

    q = db.query(
        Project.client_id,
        func.sum(revenue_expr).label("revenue")
    ).join(
        Imputation,
        Imputation.project_id == Project.id
    ).filter(
        Imputation.date.between(d_from, d_to),
        Project.is_billable.is_(True),
        Project.billing_rate.isnot(None)
    ).group_by(Project.client_id)

    if project_ids is not None:
        q = q.filter(Project.id.in_(project_ids))

    # Get client names
    client_q = db.query(Client.id, Client.name)
    client_names = {c.id: c.name for c in client_q.all()}

    rows = []
    for r in q.order_by(func.sum(revenue_expr).desc()).limit(top_n).all():
        if r.client_id:
            rows.append({
                "label": client_names.get(r.client_id, f"Cliente {r.client_id}"),
                "value": round(r.revenue or 0, 0)
            })

    return rows, {}
