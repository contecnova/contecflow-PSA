"""Revenue and Expenses metrics: revenue_recognized_by_month, revenue_by_contract,
expenses_by_category, expenses_by_project, expenses_billable_vs_internal,
expenses_trend, expenses_pending_approval."""
from datetime import date
from typing import Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from . import register_metric


@register_metric("revenue_recognized_by_month")
def metric_revenue_recognized_by_month(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Ingresos reconocidos por mes según ASC-606 (rev_entries)."""
    try:
        from app.models.revenue import RevenueEntry

        q = db.query(
            RevenueEntry.period_year,
            RevenueEntry.period_month,
            func.sum(RevenueEntry.amount).label("total"),
        ).filter(
            RevenueEntry.period_year * 100 + RevenueEntry.period_month >=
                d_from.year * 100 + d_from.month,
            RevenueEntry.period_year * 100 + RevenueEntry.period_month <=
                d_to.year * 100 + d_to.month,
        ).group_by(RevenueEntry.period_year, RevenueEntry.period_month).order_by(
            RevenueEntry.period_year, RevenueEntry.period_month
        )

        rows = []
        for r in q.all():
            rows.append({
                "label": f"{r.period_year}-{r.period_month:02d}",
                "value": round(float(r.total or 0), 2),
            })
    except Exception:
        rows = []

    return rows, {"y_label": "Ingreso reconocido (€)"}


@register_metric("revenue_by_contract")
def metric_revenue_by_contract(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Ingresos reconocidos acumulados por contrato."""
    try:
        from app.models.revenue import RevenueEntry, RevenueContract

        q = db.query(
            RevenueEntry.rev_contract_id,
            func.sum(RevenueEntry.amount).label("total"),
        ).filter(
            RevenueEntry.period_year * 100 + RevenueEntry.period_month >=
                d_from.year * 100 + d_from.month,
            RevenueEntry.period_year * 100 + RevenueEntry.period_month <=
                d_to.year * 100 + d_to.month,
        ).group_by(RevenueEntry.rev_contract_id).order_by(
            func.sum(RevenueEntry.amount).desc()
        ).limit(top_n)

        contract_ids = [r.rev_contract_id for r in q.all()]
        contracts_map = {
            c.id: c.name for c in db.query(RevenueContract).filter(
                RevenueContract.id.in_(contract_ids)
            ).all()
        } if contract_ids else {}

        rows = []
        for r in q.all():
            rows.append({
                "label": contracts_map.get(r.rev_contract_id, str(r.rev_contract_id)),
                "value": round(float(r.total or 0), 2),
            })
    except Exception:
        rows = []

    return rows, {"y_label": "Ingreso reconocido (€)"}


@register_metric("expenses_by_category")
def metric_expenses_by_category(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Gastos totales agrupados por categoría."""
    try:
        from app.models.expenses import Expense

        q_base = db.query(
            Expense.category,
            func.sum(Expense.amount).label("total"),
            func.count(Expense.id).label("count"),
        ).filter(
            Expense.expense_date >= d_from,
            Expense.expense_date <= d_to,
        )
        if project_id:
            q_base = q_base.filter(Expense.project_id == project_id)
        elif project_ids:
            q_base = q_base.filter(Expense.project_id.in_(project_ids))

        q_base = q_base.group_by(Expense.category).order_by(func.sum(Expense.amount).desc()).limit(top_n)

        rows = [
            {"label": r.category or "Sin categoría", "value": round(float(r.total or 0), 2), "count": r.count}
            for r in q_base.all()
        ]
    except Exception:
        rows = []

    return rows, {"y_label": "Importe (€)"}


@register_metric("expenses_by_project")
def metric_expenses_by_project(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Gastos totales por proyecto."""
    try:
        from app.models.expenses import Expense
        from app.models.project import Project

        # Revisión 2026-11: con reparto entre proyectos cuenta la parte de cada uno.
        from app.services.gastos_avanzados import totales_por_proyecto
        from app.models.expenses import ExpenseAllocation
        if project_ids:
            candidatos = list(project_ids)
        else:
            candidatos = {pid for (pid,) in db.query(Expense.project_id).filter(
                Expense.expense_date >= d_from, Expense.expense_date <= d_to, Expense.project_id.isnot(None)).distinct()}
            candidatos |= {pid for (pid,) in db.query(ExpenseAllocation.project_id).join(
                Expense, Expense.id == ExpenseAllocation.expense_id).filter(
                Expense.expense_date >= d_from, Expense.expense_date <= d_to).distinct()}
            candidatos = list(candidatos)
        totales = totales_por_proyecto(db, candidatos, desde=d_from, hasta=d_to)
        orden = sorted(totales.items(), key=lambda x: -x[1])[:top_n]
        proj_map = {p.id: p.name for p in db.query(Project).filter(Project.id.in_([k for k, _ in orden])).all()} if orden else {}
        rows = [{"label": proj_map.get(pid, str(pid)), "value": round(float(v), 2)} for pid, v in orden]
    except Exception:
        rows = []

    return rows, {"y_label": "Importe (€)"}


@register_metric("expenses_billable_vs_internal")
def metric_expenses_billable_vs_internal(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Comparativa de gastos facturables vs internos."""
    try:
        from app.models.expenses import Expense

        q_base = db.query(
            Expense.is_billable,
            func.sum(Expense.amount).label("total"),
            func.count(Expense.id).label("count"),
        ).filter(
            Expense.expense_date >= d_from,
            Expense.expense_date <= d_to,
        )
        if project_ids:
            q_base = q_base.filter(Expense.project_id.in_(project_ids))
        q_base = q_base.group_by(Expense.is_billable)

        rows = []
        for r in q_base.all():
            rows.append({
                "label": "Facturable" if r.is_billable else "Interno",
                "value": round(float(r.total or 0), 2),
                "count": r.count,
            })
    except Exception:
        rows = []

    return rows, {}


@register_metric("expenses_trend")
def metric_expenses_trend(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Evolución mensual del total de gastos aprobados."""
    try:
        from app.models.expenses import Expense
        from sqlalchemy import extract

        q = db.query(
            extract("year", Expense.expense_date).label("year"),
            extract("month", Expense.expense_date).label("month"),
            func.sum(Expense.amount).label("total"),
        ).filter(
            Expense.expense_date >= d_from,
            Expense.expense_date <= d_to,
            Expense.status == "approved",
        )
        if project_ids:
            q = q.filter(Expense.project_id.in_(project_ids))
        q = q.group_by("year", "month").order_by("year", "month")

        rows = []
        for r in q.all():
            rows.append({
                "label": f"{int(r.year)}-{int(r.month):02d}",
                "value": round(float(r.total or 0), 2),
            })
    except Exception:
        rows = []

    return rows, {"y_label": "Gastos aprobados (€)"}


@register_metric("expenses_pending_approval")
def metric_expenses_pending_approval(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Gastos pendientes de aprobación por persona."""
    try:
        from app.models.expenses import Expense
        from app.models.user import User

        q = db.query(
            Expense.user_id,
            func.sum(Expense.amount).label("total"),
            func.count(Expense.id).label("count"),
        ).filter(
            Expense.status == "submitted",
        ).group_by(Expense.user_id).order_by(func.sum(Expense.amount).desc()).limit(top_n)

        user_ids = [r.user_id for r in q.all()]
        users_map = {u.id: u.full_name or u.email for u in db.query(User).filter(User.id.in_(user_ids)).all()} if user_ids else {}

        rows = []
        for r in q.all():
            rows.append({
                "label": users_map.get(r.user_id, str(r.user_id)),
                "value": round(float(r.total or 0), 2),
                "count": r.count,
            })
    except Exception:
        rows = []

    return rows, {"y_label": "Importe pendiente (€)"}
