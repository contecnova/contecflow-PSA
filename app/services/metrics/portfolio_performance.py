"""Portfolio, Performance review, Timesheet and Absence metrics:
portfolio_budget_usage, performance_scores_by_person,
performance_cycle_completion_rate, timesheets_approval_rate,
timesheets_billable_hours_trend, absences_by_type, absences_by_person."""
from datetime import date
from typing import Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from . import register_metric


@register_metric("portfolio_budget_usage")
def metric_portfolio_budget_usage(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Presupuesto total vs gastado por portfolio."""
    try:
        from app.models.portfolio import Portfolio

        portfolios = db.query(Portfolio).filter(
            Portfolio.status.notin_(["closed", "cancelled"])
        ).limit(top_n).all()

        rows = []
        for p in portfolios:
            total = float(p.budget_total or 0)
            spent = float(p.budget_spent or 0)
            pct = round(spent / total * 100, 1) if total else 0
            rows.append({
                "label": p.name,
                "value": spent,
                "budget": total,
                "pct_used": pct,
            })
        rows.sort(key=lambda x: x["pct_used"], reverse=True)
    except Exception:
        rows = []
    return rows, {"y_label": "Gasto (€)"}


@register_metric("performance_scores_by_person")
def metric_performance_scores_by_person(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Score global de la última evaluación por persona."""
    try:
        from app.models.performance import PerformanceReview
        from app.models.user import User

        subq = db.query(
            PerformanceReview.reviewee_id,
            func.max(PerformanceReview.submitted_at).label("latest"),
        ).filter(
            PerformanceReview.status == "completed",
            PerformanceReview.submitted_at >= d_from,
            PerformanceReview.submitted_at <= d_to,
        ).group_by(PerformanceReview.reviewee_id).subquery()

        reviews = db.query(PerformanceReview).join(
            subq,
            (PerformanceReview.reviewee_id == subq.c.reviewee_id) &
            (PerformanceReview.submitted_at == subq.c.latest)
        ).limit(top_n).all()

        user_ids = [r.reviewee_id for r in reviews]
        users_map = {u.id: u.full_name or u.email for u in db.query(User).filter(User.id.in_(user_ids)).all()} if user_ids else {}

        rows = []
        for rev in sorted(reviews, key=lambda r: r.score_overall or 0, reverse=True):
            rows.append({
                "label": users_map.get(rev.reviewee_id, str(rev.reviewee_id)),
                "value": round(float(rev.score_overall or 0), 1),
                "score_quality": round(float(rev.score_quality or 0), 1),
                "score_delivery": round(float(rev.score_delivery or 0), 1),
                "score_teamwork": round(float(rev.score_teamwork or 0), 1),
            })
    except Exception:
        rows = []
    return rows, {"y_label": "Score global (0-10)"}


@register_metric("performance_cycle_completion_rate")
def metric_performance_cycle_completion_rate(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Porcentaje de evaluaciones completadas por ciclo de revisión."""
    try:
        from app.models.performance import PerformanceReview, ReviewCycle

        cycles = db.query(ReviewCycle).filter(
            ReviewCycle.start_date >= d_from,
            ReviewCycle.start_date <= d_to,
        ).limit(top_n).all()
        cycle_ids = [c.id for c in cycles]
        cycle_map = {c.id: c.name for c in cycles}

        total_q = {r[0]: r[1] for r in db.query(
            PerformanceReview.cycle_id, func.count(PerformanceReview.id)
        ).filter(PerformanceReview.cycle_id.in_(cycle_ids)).group_by(PerformanceReview.cycle_id).all()}

        done_q = {r[0]: r[1] for r in db.query(
            PerformanceReview.cycle_id, func.count(PerformanceReview.id)
        ).filter(
            PerformanceReview.cycle_id.in_(cycle_ids),
            PerformanceReview.status == "completed",
        ).group_by(PerformanceReview.cycle_id).all()}

        rows = []
        for cid in cycle_ids:
            total = total_q.get(cid, 0)
            done = done_q.get(cid, 0)
            rate = round(done / total * 100, 1) if total else 0
            rows.append({
                "label": cycle_map[cid],
                "value": rate,
                "total": total,
                "completed": done,
            })
        rows.sort(key=lambda x: x["value"], reverse=True)
    except Exception:
        rows = []
    return rows, {"y_label": "Completado (%)"}


@register_metric("timesheets_approval_rate")
def metric_timesheets_approval_rate(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Distribución de partes de horas por estado."""
    try:
        from app.models.financial import Timesheet

        q = db.query(Timesheet.status, func.count(Timesheet.id).label("cnt")).filter(
            Timesheet.week_start >= d_from,
            Timesheet.week_start <= d_to,
        ).group_by(Timesheet.status).order_by(func.count(Timesheet.id).desc())

        rows = [{"label": r.status or "Sin estado", "value": r.cnt} for r in q.all()]
    except Exception:
        rows = []
    return rows, {}


@register_metric("timesheets_billable_hours_trend")
def metric_timesheets_billable_hours_trend(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Evolución mensual de horas facturables aprobadas (timesheets)."""
    try:
        from app.models.financial import Timesheet
        from sqlalchemy import extract

        q = db.query(
            extract("year", Timesheet.week_start).label("year"),
            extract("month", Timesheet.week_start).label("month"),
            func.sum(Timesheet.billable_hours).label("billable"),
            func.sum(Timesheet.total_hours).label("total"),
        ).filter(
            Timesheet.week_start >= d_from,
            Timesheet.week_start <= d_to,
            Timesheet.status == "approved",
        ).group_by("year", "month").order_by("year", "month")

        rows = [
            {
                "label": f"{int(r.year)}-{int(r.month):02d}",
                "value": round(float(r.billable or 0), 1),
                "total_hours": round(float(r.total or 0), 1),
            }
            for r in q.all()
        ]
    except Exception:
        rows = []
    return rows, {"y_label": "Horas facturables"}


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
    """Días de ausencia agrupados por tipo (vacaciones, baja, etc.)."""
    try:
        from app.models.resources import Absence

        q = db.query(
            Absence.type,
            func.sum(Absence.working_days).label("days"),
            func.count(Absence.id).label("cnt"),
        ).filter(
            Absence.start_date >= d_from,
            Absence.start_date <= d_to,
            Absence.status == "approved",
        ).group_by(Absence.type).order_by(func.sum(Absence.working_days).desc())

        rows = [
            {"label": r.type or "Sin tipo", "value": round(float(r.days or 0), 1), "count": r.cnt}
            for r in q.all()
        ]
    except Exception:
        rows = []
    return rows, {"y_label": "Días laborables"}


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
    """Días de ausencia aprobados por persona en el período."""
    try:
        from app.models.resources import Absence
        from app.models.user import User

        q = db.query(
            Absence.user_id,
            func.sum(Absence.working_days).label("days"),
        ).filter(
            Absence.start_date >= d_from,
            Absence.start_date <= d_to,
            Absence.status == "approved",
        ).group_by(Absence.user_id).order_by(func.sum(Absence.working_days).desc()).limit(top_n)

        user_ids = [r.user_id for r in q.all()]
        users_map = {u.id: u.full_name or u.email for u in db.query(User).filter(User.id.in_(user_ids)).all()} if user_ids else {}

        rows = [
            {"label": users_map.get(r.user_id, str(r.user_id)), "value": round(float(r.days or 0), 1)}
            for r in q.all()
        ]
    except Exception:
        rows = []
    return rows, {"y_label": "Días laborables"}
