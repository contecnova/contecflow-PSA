"""
dashboard_service.py — Lógica de negocio para KPIs y analytics del dashboard.

Funciones exportadas:
  get_global_kpis(db) -> DashboardKPIs
  get_projects_health(db) -> list[ProjectHealthItem]
  get_resource_load(week_start, department, db) -> list[ResourceLoadItem]
  get_profitability(date_from, date_to, db) -> list[dict]
  get_team_productivity(date_from, date_to, department, db) -> dict
"""
from __future__ import annotations

from datetime import date, timedelta
from threading import Lock
from typing import Optional

from cachetools import TTLCache
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings

# ── KPI cache ──────────────────────────────────────────────────────────────────
_kpi_cache: TTLCache = TTLCache(maxsize=64, ttl=60)
_kpi_cache_lock = Lock()


# ── KPIs ───────────────────────────────────────────────────────────────────────

def get_global_kpis(db: Session):
    from app.models.project import Project, ProjectStatus, ProjectRisk
    from app.models.imputation import Imputation
    from app.models.task import Task, TaskStatus
    from app.models.user import User, UserStatus
    from app.models.alert import Alert
    from app.schemas.schemas import DashboardKPIs

    cache_key = date.today().isoformat()
    with _kpi_cache_lock:
        if cache_key in _kpi_cache:
            return _kpi_cache[cache_key]

    today = date.today()
    week_start = today - timedelta(days=today.weekday())

    total_budget = db.query(func.sum(Project.budget_amount)).filter(
        Project.status == ProjectStatus.active
    ).scalar() or 0.0

    active_project_ids = db.query(Project.id).filter(
        Project.status == ProjectStatus.active
    ).scalar_subquery()
    total_spent = db.query(func.sum(Imputation.cost_amount)).filter(
        Imputation.project_id.in_(active_project_ids)
    ).scalar() or 0.0
    budget_used_pct = round((total_spent / total_budget) * 100, 1) if total_budget > 0 else 0

    projects_active = db.query(func.count(Project.id)).filter(
        Project.status == ProjectStatus.active
    ).scalar() or 0

    projects_at_risk = db.query(func.count(Project.id)).filter(
        Project.status == ProjectStatus.active,
        Project.risk_level.in_([ProjectRisk.high, ProjectRisk.critical]),
    ).scalar() or 0

    total_resources = db.query(func.count(User.id)).filter(
        User.is_active == True, User.status == UserStatus.active
    ).scalar() or 0

    week_hours = db.query(
        Imputation.user_id,
        func.sum(Imputation.hours).label("total"),
    ).filter(Imputation.date >= week_start).group_by(Imputation.user_id).subquery()

    overloaded = db.query(func.count(User.id)).join(
        week_hours, week_hours.c.user_id == User.id
    ).filter(
        User.is_active == True,
        week_hours.c.total >= User.weekly_capacity_hours,
    ).scalar() or 0

    tasks_blocked = db.query(func.count(Task.id)).filter(
        Task.status == TaskStatus.blocked
    ).scalar() or 0

    tasks_overdue = db.query(func.count(Task.id)).filter(
        Task.due_date < today,
        Task.status.not_in([TaskStatus.done, TaskStatus.cancelled]),
    ).scalar() or 0

    hours_this_week = db.query(func.sum(Imputation.hours)).filter(
        Imputation.date >= week_start
    ).scalar() or 0.0

    efficiency_data = db.query(
        func.sum(Imputation.hours).label("real_hours"),
        func.sum(Task.estimated_hours).label("estimated_hours"),
    ).join(Task, Task.id == Imputation.task_id).filter(
        Task.status == TaskStatus.done,
        Task.estimated_hours > 0,
    ).first()
    if efficiency_data and efficiency_data.real_hours and efficiency_data.estimated_hours:
        avg_efficiency = round(efficiency_data.estimated_hours / efficiency_data.real_hours, 2)
    else:
        avg_efficiency = 0.0

    projects_over_budget = 0
    active_projects_list = db.query(Project).filter(Project.status == ProjectStatus.active).all()
    for p in active_projects_list:
        if p.budget_amount and p.budget_amount > 0:
            cost = db.query(func.sum(Imputation.cost_amount)).filter(
                Imputation.project_id == p.id
            ).scalar() or 0.0
            if cost > p.budget_amount:
                projects_over_budget += 1

    result = DashboardKPIs(
        total_budget=total_budget,
        total_spent=total_spent,
        budget_used_pct=budget_used_pct,
        projects_active=projects_active,
        projects_at_risk=projects_at_risk,
        projects_over_budget=projects_over_budget,
        total_resources=total_resources,
        overloaded_resources=overloaded,
        avg_load_pct=0.0,
        tasks_blocked=tasks_blocked,
        tasks_overdue=tasks_overdue,
        avg_efficiency_ratio=avg_efficiency,
        hours_logged_this_week=hours_this_week,
    )
    with _kpi_cache_lock:
        _kpi_cache[cache_key] = result
    return result


# ── Projects health ────────────────────────────────────────────────────────────

def _project_health_score(
    budget_used_pct: float,
    deviation_days: int,
    alerts_count: int,
    risk_level_value: str,
    progress_pct: float,
) -> int:
    score = 100
    if budget_used_pct > 100:
        score -= min(30, int(budget_used_pct - 80))
    elif budget_used_pct > 80:
        score -= int((budget_used_pct - 80) * 0.8)
    if deviation_days > 30:
        score -= 25
    elif deviation_days > 14:
        score -= 15
    elif deviation_days > 7:
        score -= 10
    elif deviation_days > 0:
        score -= 5
    score -= min(20, alerts_count * 5)
    score -= {"critical": 15, "high": 8, "medium": 3, "low": 0}.get(risk_level_value, 0)
    if progress_pct >= 80:
        score += 5
    return max(0, min(100, score))


def get_projects_health(db: Session) -> list:
    from app.models.project import Project, ProjectStatus
    from app.models.imputation import Imputation
    from app.models.task import Task, TaskStatus
    from app.models.alert import Alert
    from app.schemas.schemas import ProjectHealthItem

    projects = db.query(Project).filter(Project.status == ProjectStatus.active).all()
    if not projects:
        return []

    project_ids = [p.id for p in projects]
    today = date.today()

    cost_rows = db.query(
        Imputation.project_id,
        func.sum(Imputation.cost_amount).label("total_cost"),
    ).filter(Imputation.project_id.in_(project_ids)).group_by(Imputation.project_id).all()
    cost_by_pid = {r.project_id: float(r.total_cost or 0) for r in cost_rows}

    task_total_rows = db.query(
        Task.project_id, func.count(Task.id).label("cnt"),
    ).filter(Task.project_id.in_(project_ids)).group_by(Task.project_id).all()
    task_total_by_pid = {r.project_id: r.cnt for r in task_total_rows}

    task_done_rows = db.query(
        Task.project_id, func.count(Task.id).label("cnt"),
    ).filter(Task.project_id.in_(project_ids), Task.status == TaskStatus.done).group_by(Task.project_id).all()
    task_done_by_pid = {r.project_id: r.cnt for r in task_done_rows}

    team_rows = db.query(
        Imputation.project_id,
        func.count(func.distinct(Imputation.user_id)).label("cnt"),
    ).filter(Imputation.project_id.in_(project_ids)).group_by(Imputation.project_id).all()
    team_by_pid = {r.project_id: r.cnt for r in team_rows}

    alert_rows = db.query(
        Alert.project_id, func.count(Alert.id).label("cnt"),
    ).filter(Alert.project_id.in_(project_ids), Alert.is_resolved == False).group_by(Alert.project_id).all()
    alert_by_pid = {r.project_id: r.cnt for r in alert_rows}

    result = []
    for p in projects:
        total_cost = cost_by_pid.get(p.id, 0.0)
        tasks_total = task_total_by_pid.get(p.id, 0)
        tasks_done = task_done_by_pid.get(p.id, 0)
        team_size = team_by_pid.get(p.id, 0)
        alerts_count = alert_by_pid.get(p.id, 0)
        progress_pct = round((tasks_done / tasks_total) * 100, 1) if tasks_total > 0 else 0.0

        budget_used_pct = 0.0
        if p.budget_amount and p.budget_amount > 0:
            budget_used_pct = round((total_cost / p.budget_amount) * 100, 1)

        deviation_days = 0
        if p.end_date_planned and today > p.end_date_planned:
            deviation_days = (today - p.end_date_planned).days

        health_score = _project_health_score(
            budget_used_pct, deviation_days, alerts_count,
            p.risk_level.value if p.risk_level else "low",
            progress_pct,
        )

        result.append(ProjectHealthItem(
            project_id=p.id,
            project_name=p.name,
            project_code=p.code,
            budget_used_pct=budget_used_pct,
            schedule_deviation_days=deviation_days,
            risk_level=p.risk_level.value if p.risk_level else "low",
            status=p.status.value,
            team_size=team_size,
            alerts_count=alerts_count,
            tasks_total=tasks_total,
            tasks_done=tasks_done,
            progress_pct=progress_pct,
            health_score=health_score,
        ))

    return result


# ── Resource load ──────────────────────────────────────────────────────────────

def get_resource_load(
    week_start: Optional[date],
    department: Optional[str],
    db: Session,
) -> list:
    from app.models.user import User, UserStatus
    from app.models.imputation import Imputation
    from app.models.task import Task, TaskStatus
    from app.schemas.schemas import ResourceLoadItem

    if not week_start:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    q = db.query(User).filter(User.is_active == True, User.status == UserStatus.active)
    if department:
        q = q.filter(User.department == department)
    users = q.all()

    result = []
    for user in users:
        hours_week = db.query(func.sum(Imputation.hours)).filter(
            Imputation.user_id == user.id,
            Imputation.date.between(week_start, week_end),
        ).scalar() or 0.0

        if hours_week == 0:
            four_weeks_ago = week_start - timedelta(weeks=4)
            prev_week_end = week_start - timedelta(days=1)
            hours_recent = db.query(func.sum(Imputation.hours)).filter(
                Imputation.user_id == user.id,
                Imputation.date.between(four_weeks_ago, prev_week_end),
            ).scalar() or 0.0
            hours_week = round(hours_recent / 4, 1)

        capacity = user.weekly_capacity_hours or settings.DEFAULT_WEEKLY_CAPACITY_HOURS
        load_pct = round((hours_week / capacity) * 100, 1)

        active_projects = db.query(func.count(func.distinct(Imputation.project_id))).filter(
            Imputation.user_id == user.id,
            Imputation.date >= week_start,
        ).scalar() or 0

        eff_data = db.query(
            func.sum(Imputation.hours).label("real_h"),
            func.sum(Task.estimated_hours).label("est_h"),
        ).join(Task, Task.id == Imputation.task_id).filter(
            Imputation.user_id == user.id,
            Task.status == TaskStatus.done,
            Task.estimated_hours > 0,
        ).first()
        if eff_data and eff_data.real_h and eff_data.est_h:
            efficiency = round(eff_data.est_h / eff_data.real_h, 2)
        else:
            efficiency = 0.0

        result.append(ResourceLoadItem(
            user_id=user.id,
            user_name=user.full_name,
            department=user.department or "",
            load_pct=load_pct,
            hours_week=hours_week,
            active_projects=active_projects,
            efficiency=efficiency,
        ))

    return sorted(result, key=lambda x: x.load_pct, reverse=True)


# ── Profitability ──────────────────────────────────────────────────────────────

def get_profitability(
    date_from: Optional[date],
    date_to: Optional[date],
    db: Session,
) -> list:
    from app.models.project import Project, ProjectStatus
    from app.models.imputation import Imputation

    projects = db.query(Project).filter(
        Project.status.in_([ProjectStatus.active, ProjectStatus.closed])
    ).all()

    agg_q = db.query(
        Imputation.project_id.label("project_id"),
        func.sum(Imputation.cost_amount).label("total_cost"),
        func.sum(Imputation.hours).label("total_hours"),
    )
    if date_from:
        agg_q = agg_q.filter(Imputation.date >= date_from)
    if date_to:
        agg_q = agg_q.filter(Imputation.date <= date_to)
    aggregates = {
        row.project_id: (row.total_cost or 0, row.total_hours or 0)
        for row in agg_q.group_by(Imputation.project_id).all()
    }

    result = []
    for p in projects:
        cost, hours = aggregates.get(p.id, (0, 0))
        revenue = (hours or 0) * (p.billing_rate or 0) if p.is_billable else 0
        margin = revenue - (cost or 0)
        margin_pct = round((margin / revenue) * 100, 1) if revenue > 0 else None
        result.append({
            "project_id": p.id,
            "project_code": p.code,
            "project_name": p.name,
            "is_billable": p.is_billable,
            "budget_amount": p.budget_amount,
            "total_cost": cost or 0,
            "total_hours": hours or 0,
            "revenue": revenue,
            "margin": margin,
            "margin_pct": margin_pct,
        })

    return sorted(result, key=lambda x: x["total_cost"], reverse=True)


# ── Team productivity ──────────────────────────────────────────────────────────

def get_team_productivity(
    date_from: Optional[date],
    date_to: Optional[date],
    department: Optional[str],
    db: Session,
) -> dict:
    from app.models.user import User
    from app.models.imputation import Imputation
    from app.models.task import Task, TaskStatus

    if not date_from:
        date_from = date.today().replace(day=1)
    if not date_to:
        date_to = date.today()

    q = db.query(User).filter(User.is_active == True)
    if department:
        q = q.filter(User.department == department)
    users = q.all()

    result = []
    for user in users:
        hours = db.query(func.sum(Imputation.hours)).filter(
            Imputation.user_id == user.id,
            Imputation.date.between(date_from, date_to),
        ).scalar() or 0.0

        tasks_done = db.query(func.count(Task.id)).filter(
            Task.assignee_id == user.id,
            Task.status == TaskStatus.done,
        ).scalar() or 0

        result.append({
            "user_id": user.id,
            "user_name": user.full_name,
            "department": user.department,
            "job_title": user.job_title,
            "hours_logged": hours,
            "tasks_completed": tasks_done,
        })

    return {"period_start": date_from, "period_end": date_to, "team_stats": result}
