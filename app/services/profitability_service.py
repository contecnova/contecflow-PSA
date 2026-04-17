"""
profitability_service.py — DB access layer for profitability & milestone operations.
All db.query/add/commit/delete/flush calls live here; the router stays free of ORM calls.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func, case
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.models.financial import ProjectMilestone
from app.models.imputation import Imputation
from app.models.bookings import ExchangeRate
from app.models.project import Project, ProjectStatus
from app.models.task import TaskStatus
from app.models.user import User

# ── FX helper ──────────────────────────────────────────────────────────────────

# Kept as empty module-level name for backward compatibility with existing imports/tests.
# Production code uses a call-local cache (passed as parameter) to avoid shared mutable state.
_fx_cache: dict = {}


def get_fx_rate(
    db: Session,
    from_currency: str,
    to_currency: str,
    as_of: date,
    _cache: dict | None = None,
) -> float:
    """Return FX rate for *from_currency* → *to_currency* on *as_of*.

    *_cache* is an optional call-local dict used to avoid redundant DB hits within
    the same computation.  Pass an explicit dict from the caller; never share one
    across concurrent requests.
    """
    if from_currency == to_currency:
        return 1.0
    key = (from_currency, to_currency, as_of)
    if _cache is not None and key in _cache:
        return _cache[key]
    row = (
        db.query(ExchangeRate)
        .filter(
            ExchangeRate.from_currency == from_currency,
            ExchangeRate.to_currency == to_currency,
            ExchangeRate.effective_date <= as_of,
        )
        .order_by(ExchangeRate.effective_date.desc())
        .first()
    )
    rate = row.rate if row else 1.0
    if _cache is not None:
        _cache[key] = rate
    return rate


# ── Profitability calculation (pure after DB fetch) ────────────────────────────

def calc_project_profitability(
    project: Project,
    db: Session,
    imputation_totals: Optional[dict] = None,
    billed_milestones_total: Optional[float] = None,
) -> dict:
    """Calculate full P&L for a project.

    Costs are normalised to *settings.DEFAULT_CURRENCY* using the exchange rate
    effective on the imputation date.
    """
    # Local cache: isolated per call, no shared mutable state between concurrent requests.
    _local_fx_cache: dict = {}

    org_currency = settings.DEFAULT_CURRENCY
    project_currency = getattr(project, "currency", org_currency) or org_currency

    if imputation_totals is None or project_currency != org_currency:
        imps = get_project_imputations(db, project.id)
        total_hours = sum(i.hours for i in imps)
        billable_hours = sum(i.hours for i in imps if i.is_billable)
        # Bulk-load users so we can read their currency for FX conversion
        user_ids = {i.user_id for i in imps if i.user_id}
        if user_ids:
            user_currency_map = {
                u.id: (getattr(u, "currency", None) or org_currency)
                for u in db.query(User).filter(User.id.in_(user_ids)).all()
            }
        else:
            user_currency_map = {}
        internal_cost = 0.0
        for i in imps:
            raw_cost = i.cost_amount or 0.0
            if raw_cost:
                # Convert from the user's native currency to the org's default currency
                user_currency = user_currency_map.get(i.user_id, org_currency) or org_currency
                if user_currency != org_currency:
                    fx = get_fx_rate(db, user_currency, org_currency, i.date, _cache=_local_fx_cache)
                    raw_cost = raw_cost * fx
                elif project_currency != org_currency:
                    # Fallback: convert based on project currency when user currency is unknown
                    fx = get_fx_rate(db, project_currency, org_currency, i.date, _cache=_local_fx_cache)
                    raw_cost = raw_cost * fx
            internal_cost += raw_cost
    else:
        total_hours = float(imputation_totals.get("total_hours") or 0)
        billable_hours = float(imputation_totals.get("billable_hours") or 0)
        internal_cost = float(imputation_totals.get("internal_cost") or 0)

    billing_revenue = 0
    if project.billing_rate and billable_hours:
        billing_revenue = project.billing_rate * billable_hours
    elif project.contract_amount:
        if billed_milestones_total is None:
            milestones = get_billed_milestones(db, project.id)
            billing_revenue = sum(m.billing_amount or 0 for m in milestones)
        else:
            billing_revenue = float(billed_milestones_total or 0)

    gross_margin = billing_revenue - internal_cost
    margin_pct = (gross_margin / billing_revenue * 100) if billing_revenue > 0 else 0

    budget_used_pct = 0
    if project.budget_amount and project.budget_amount > 0:
        budget_used_pct = (internal_cost / project.budget_amount) * 100

    tasks = project.tasks if hasattr(project, "tasks") else []
    progress = 0
    if tasks:
        weighted_done = 0.0
        for t in tasks:
            if t.status == TaskStatus.done:
                weighted_done += 1.0
            elif t.status == TaskStatus.in_progress:
                weighted_done += 0.5
            elif t.status == TaskStatus.review:
                weighted_done += 0.8
            elif t.status in [TaskStatus.todo, TaskStatus.backlog, TaskStatus.blocked, TaskStatus.cancelled]:
                weighted_done += 0.0
        progress = (weighted_done / len(tasks)) * 100 if tasks else 0

    forecast_cost = 0
    if progress >= 5.0:
        remaining_pct = 100 - progress
        forecast_cost = round(internal_cost + (internal_cost * remaining_pct / progress), 2)
    elif total_hours > 0 and project.budget_hours:
        forecast_cost = round((internal_cost / total_hours) * project.budget_hours, 2)

    today = date.today()
    if project.start_date and project.end_date_planned and project.end_date_planned > project.start_date:
        total_days = (project.end_date_planned - project.start_date).days
        elapsed_days = max(0, (today - project.start_date).days)
        planned_pct = min(100, (elapsed_days / total_days) * 100)
    else:
        planned_pct = None

    pv = round((project.budget_amount or 0) * planned_pct / 100, 2) if planned_pct is not None else None
    ev = round((project.budget_amount or 0) * progress / 100, 2) if progress > 0 else 0
    ac = round(internal_cost, 2)

    cpi = round(ev / ac, 3) if ac > 0 else None
    spi = round(ev / pv, 3) if (pv is not None and pv > 0) else None

    budget_at_completion = project.budget_amount or forecast_cost or 0
    if cpi and cpi > 0:
        eac = round(ac + (budget_at_completion - ev) / cpi, 2)
    elif progress >= 1.0:
        eac = round(ac / (progress / 100), 2)
    else:
        eac = budget_at_completion

    etc = round(max(eac - ac, 0), 2)
    vac = round(budget_at_completion - eac, 2)
    cv = round(ev - ac, 2)
    sv = round(ev - pv, 2) if pv is not None else None

    margin_at_completion = 0
    if billing_revenue > 0 and eac > 0:
        margin_at_completion = round((billing_revenue - eac) / billing_revenue * 100, 1)

    risk_flag = (
        "critical" if (cpi and cpi < 0.8) or margin_at_completion < 0 else
        "warning" if (cpi and cpi < 0.95) or margin_at_completion < 10 else
        "ok"
    )

    return {
        "project_id": project.id,
        "project_code": project.code,
        "project_name": project.name,
        "client_name": project.client_name,
        "department": project.department,
        "status": project.status,
        "billing_type": project.billing_type or "time_material",
        "is_billable": project.is_billable,
        "project_currency": project_currency,
        "reporting_currency": org_currency,
        "total_hours": round(total_hours, 1),
        "billable_hours": round(billable_hours, 1),
        "budget_hours": project.budget_hours,
        "hours_used_pct": round((total_hours / project.budget_hours * 100), 1) if project.budget_hours else None,
        "internal_cost": round(internal_cost, 2),
        "billing_revenue": round(billing_revenue, 2),
        "gross_margin": round(gross_margin, 2),
        "margin_pct": round(margin_pct, 1),
        "budget_amount": project.budget_amount,
        "contract_amount": project.contract_amount,
        "budget_used_pct": round(budget_used_pct, 1),
        "forecast_cost": round(forecast_cost, 2),
        "billing_rate": project.billing_rate,
        "avg_cost_rate": round(internal_cost / total_hours, 2) if total_hours > 0 else 0,
        "progress_pct": round(progress, 1),
        "pv": pv,
        "ev": ev,
        "ac": ac,
        "cpi": cpi,
        "spi": spi,
        "cv": cv,
        "sv": sv,
        "evm_no_schedule": planned_pct is None,
        "eac": eac,
        "etc": etc,
        "vac": vac,
        "margin_at_completion": margin_at_completion,
        "risk_flag": risk_flag,
    }


# ── Imputation queries ─────────────────────────────────────────────────────────

def get_project_imputations(db: Session, project_id: str) -> list:
    return db.query(Imputation).filter(Imputation.project_id == project_id).all()


def get_imputation_totals_by_project(db: Session, project_ids: list) -> dict:
    if not project_ids:
        return {}
    rows = (
        db.query(
            Imputation.project_id.label("project_id"),
            func.sum(Imputation.hours).label("total_hours"),
            func.sum(case((Imputation.is_billable == True, Imputation.hours), else_=0)).label("billable_hours"),
            func.sum(Imputation.cost_amount).label("internal_cost"),
        )
        .filter(Imputation.project_id.in_(project_ids))
        .group_by(Imputation.project_id)
        .all()
    )
    return {
        r.project_id: {
            "total_hours": r.total_hours,
            "billable_hours": r.billable_hours,
            "internal_cost": r.internal_cost,
        }
        for r in rows
    }


def get_imputations_by_person(db: Session, project_id: str) -> list:
    return (
        db.query(
            Imputation.user_id,
            User.full_name,
            func.sum(Imputation.hours).label("hours"),
            func.sum(Imputation.cost_amount).label("cost"),
        )
        .join(User, User.id == Imputation.user_id)
        .filter(Imputation.project_id == project_id)
        .group_by(Imputation.user_id, User.full_name)
        .all()
    )


def get_imputations_by_day(db: Session, project_id: str) -> list:
    return (
        db.query(
            Imputation.date,
            func.sum(Imputation.hours).label("hours"),
            func.sum(Imputation.cost_amount).label("cost"),
        )
        .filter(Imputation.project_id == project_id)
        .group_by(Imputation.date)
        .order_by(Imputation.date)
        .all()
    )


# ── Milestone queries ──────────────────────────────────────────────────────────

def get_billed_milestones(db: Session, project_id: str) -> list:
    return (
        db.query(ProjectMilestone)
        .filter(ProjectMilestone.project_id == project_id, ProjectMilestone.is_billed == True)
        .all()
    )


def get_billed_milestones_total_by_project(db: Session, project_ids: list) -> dict:
    if not project_ids:
        return {}
    rows = (
        db.query(
            ProjectMilestone.project_id.label("project_id"),
            func.sum(ProjectMilestone.billing_amount).label("billing_revenue"),
        )
        .filter(
            ProjectMilestone.project_id.in_(project_ids),
            ProjectMilestone.is_billed == True,
        )
        .group_by(ProjectMilestone.project_id)
        .all()
    )
    return {r.project_id: r.billing_revenue for r in rows}


def list_milestones(db: Session, project_id: str) -> list:
    return (
        db.query(ProjectMilestone)
        .filter(ProjectMilestone.project_id == project_id)
        .order_by(ProjectMilestone.sort_order)
        .all()
    )


def get_milestone(db: Session, milestone_id: str, project_id: str) -> Optional[ProjectMilestone]:
    return (
        db.query(ProjectMilestone)
        .filter(ProjectMilestone.id == milestone_id, ProjectMilestone.project_id == project_id)
        .first()
    )


def create_milestone(db: Session, project_id: str, data: dict) -> ProjectMilestone:
    m = ProjectMilestone(project_id=project_id, **data)
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def update_milestone(db: Session, m: ProjectMilestone, updates: dict) -> ProjectMilestone:
    for k, v in updates.items():
        setattr(m, k, v)
    db.commit()
    db.refresh(m)
    return m


def delete_milestone(db: Session, m: ProjectMilestone) -> None:
    db.delete(m)
    db.commit()


# ── Project queries ────────────────────────────────────────────────────────────

def get_summary_projects(db: Session, status: Optional[str] = None) -> list:
    q = db.query(Project).options(joinedload(Project.tasks))
    if status:
        q = q.filter(Project.status == status)
    else:
        q = q.filter(Project.status.in_([ProjectStatus.active, ProjectStatus.closed]))
    return q.all()


def get_project_with_tasks(db: Session, project_id: str) -> Optional[Project]:
    return (
        db.query(Project)
        .options(joinedload(Project.tasks), joinedload(Project.project_manager))
        .filter(Project.id == project_id)
        .first()
    )
