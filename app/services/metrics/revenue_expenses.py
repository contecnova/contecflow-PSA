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
    """Gastos (aprobados o reembolsados) por categoría; con proyectos, su parte del reparto."""
    try:
        from app.services.gastos_avanzados import coste_en_proyectos
        ids = [project_id] if project_id else project_ids
        grupos: dict = {}
        for g, importe in coste_en_proyectos(db, d_from, d_to, ids):
            cat = str(getattr(g.category, "value", g.category) or "Sin categoría")
            total, n = grupos.get(cat, (0.0, 0))
            grupos[cat] = (total + importe, n + 1)
        rows = [{"label": k, "value": round(v, 2), "count": n}
                for k, (v, n) in sorted(grupos.items(), key=lambda x: -x[1][0])[:top_n]]
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
    """Gastos facturables frente a internos (aprobados o reembolsados); con proyectos, su parte del reparto."""
    try:
        from app.services.gastos_avanzados import coste_en_proyectos
        ids = [project_id] if project_id else project_ids
        grupos: dict = {}
        for g, importe in coste_en_proyectos(db, d_from, d_to, ids):
            total, n = grupos.get(bool(g.is_billable), (0.0, 0))
            grupos[bool(g.is_billable)] = (total + importe, n + 1)
        rows = [{"label": "Facturable" if k else "Interno", "value": round(v, 2), "count": n} for k, (v, n) in grupos.items()]
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
    """Evolución mensual de los gastos aprobados o reembolsados; con proyectos, su parte del reparto."""
    try:
        from app.services.gastos_avanzados import coste_en_proyectos
        ids = [project_id] if project_id else project_ids
        meses: dict = {}
        for g, importe in coste_en_proyectos(db, d_from, d_to, ids):
            m = f"{g.expense_date.year}-{g.expense_date.month:02d}"
            meses[m] = meses.get(m, 0.0) + importe
        rows = [{"label": m, "value": round(v, 2)} for m, v in sorted(meses.items())]
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
