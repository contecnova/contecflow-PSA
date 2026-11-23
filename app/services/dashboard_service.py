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

from app.services.settings_service.por_empresa import capacidad_semanal
from app.models.alert import Alert
from app.models.imputation import Imputation
from app.models.project import Project, ProjectStatus, ProjectRisk
from app.models.task import Task, TaskStatus
from app.models.user import User, UserStatus
from app.schemas import DashboardKPIs
from app.schemas import ProjectHealthItem
from app.schemas import ResourceLoadItem
from app.core import timeutil


def _org_id(current_user: Optional[User]) -> Optional[str]:
    """Return the organization_id to scope queries to, or None for superadmin/unscoped.

    A25 (auditoría 22-11-2026): un usuario SIN empresa que no es superadmin ya
    no cae en «sin filtro» (veía todas): devuelve una empresa imposible y las
    consultas salen vacías (falla cerrado).
    """
    if current_user is None:
        return None
    if getattr(current_user, "is_superadmin", False):
        return None
    return getattr(current_user, "organization_id", None) or _SIN_EMPRESA


#: A25: marcador de «ninguna empresa» (ningún id real coincide).
_SIN_EMPRESA = "__sin_empresa__"

# ── KPI cache ──────────────────────────────────────────────────────────────────
_kpi_cache: TTLCache = TTLCache(maxsize=64, ttl=60)
_kpi_cache_lock = Lock()


# ── KPIs ───────────────────────────────────────────────────────────────────────

def get_global_kpis(db: Session, current_user: Optional[User] = None):

    org = _org_id(current_user)
    # Revision multitenant 2026-11b: superadmin (todas) y usuario sin empresa
    # (ninguna) daban los dos `None` y compartian entrada.
    plataforma = bool(getattr(current_user, "is_superadmin", False))
    cache_key = f"{timeutil.today().isoformat()}:{org}:{'plataforma' if plataforma else 'empresa'}"
    with _kpi_cache_lock:
        if cache_key in _kpi_cache:
            return _kpi_cache[cache_key]

    today = timeutil.today()
    week_start = today - timedelta(days=today.weekday())

    proj_base = db.query(Project.id).filter(Project.status == ProjectStatus.active)
    if org:
        proj_base = proj_base.filter(Project.organization_id == org)

    total_budget = db.query(func.sum(Project.budget_amount)).filter(
        Project.status == ProjectStatus.active,
        *([Project.organization_id == org] if org else []),
    ).scalar() or 0.0

    active_project_ids = proj_base.scalar_subquery()

    org_proj_filters = [Project.organization_id == org] if org else []
    org_user_filters = [User.organization_id == org] if org else []

    projects_active = db.query(func.count(Project.id)).filter(
        Project.status == ProjectStatus.active,
        *org_proj_filters,
    ).scalar() or 0

    projects_at_risk = db.query(func.count(Project.id)).filter(
        Project.status == ProjectStatus.active,
        Project.risk_level.in_([ProjectRisk.high, ProjectRisk.critical]),
        *org_proj_filters,
    ).scalar() or 0

    total_resources = db.query(func.count(User.id)).filter(
        User.is_active == True, User.status == UserStatus.active,
        *org_user_filters,
    ).scalar() or 0

    week_hours_q = db.query(
        Imputation.user_id,
        func.sum(Imputation.hours).label("total"),
    ).filter(
        Imputation.date >= week_start, Imputation.is_active.is_(True),
        *([Imputation.project_id.in_(active_project_ids)] if org else []),
    ).group_by(Imputation.user_id).subquery()

    overloaded = db.query(func.count(User.id)).join(
        week_hours_q, week_hours_q.c.user_id == User.id
    ).filter(
        User.is_active == True,
        week_hours_q.c.total >= User.weekly_capacity_hours,
        *org_user_filters,
    ).scalar() or 0

    tasks_open = db.query(func.count(Task.id)).filter(
        Task.status.in_([TaskStatus.todo, TaskStatus.in_progress]),
        *([Task.project_id.in_(active_project_ids)] if org else []),
    ).scalar() or 0

    tasks_blocked = db.query(func.count(Task.id)).filter(
        Task.status == TaskStatus.blocked,
        *([Task.project_id.in_(active_project_ids)] if org else []),
    ).scalar() or 0

    tasks_overdue = db.query(func.count(Task.id)).filter(
        Task.due_date < today,
        Task.status.not_in([TaskStatus.done, TaskStatus.cancelled]),
        *([Task.project_id.in_(active_project_ids)] if org else []),
    ).scalar() or 0

    hours_this_week = db.query(func.sum(Imputation.hours)).filter(
        Imputation.date >= week_start, Imputation.is_active.is_(True),
        *([Imputation.project_id.in_(active_project_ids)] if org else []),
    ).scalar() or 0.0

    efficiency_data = db.query(
        func.sum(Imputation.hours).label("real_hours"),
        func.sum(Task.estimated_hours).label("estimated_hours"),
    ).join(Task, Task.id == Imputation.task_id).filter(
        Task.status == TaskStatus.done, Imputation.is_active.is_(True),
        Task.estimated_hours > 0,
        *([Task.project_id.in_(active_project_ids)] if org else []),
    ).first()
    if efficiency_data and efficiency_data.real_hours and efficiency_data.estimated_hours:
        avg_efficiency = round(efficiency_data.estimated_hours / efficiency_data.real_hours, 2)
    else:
        avg_efficiency = 0.0

    # Auditoría 22-11-2026 (§7.2 / M8): el coste es el del cálculo único en
    # bloque (personal convertido + gastos + subcontrata + ALM; antes una
    # consulta por proyecto con borradas y sin convertir).
    from app.services.margen_de_proyectos import margen_en_bloque
    active_projects_list = db.query(Project).filter(
        Project.status == ProjectStatus.active,
        *org_proj_filters,
    ).all()
    cifras = margen_en_bloque(db, active_projects_list)
    total_spent = round(sum(c["total_cost"] for c in cifras.values()), 2)
    budget_used_pct = round((total_spent / total_budget) * 100, 1) if total_budget > 0 else 0
    projects_over_budget = sum(
        1 for p in active_projects_list
        if p.budget_amount and p.budget_amount > 0 and cifras[p.id]["total_cost"] > p.budget_amount)

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
        tasks_open=tasks_open,
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
    cortes_presupuesto: tuple = (70.0, 90.0),
) -> int:
    # 19-11-2026: la penalización por presupuesto empieza en los cortes de la
    # empresa (UMBRAL_PRESUPUESTO_*, 70/90 por defecto); antes 80/100 fijos.
    aviso, critico = cortes_presupuesto
    score = 100
    if budget_used_pct > critico:
        score -= min(30, int(budget_used_pct - aviso))
    elif budget_used_pct > aviso:
        score -= int((budget_used_pct - aviso) * 0.8)
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


def get_projects_health(db: Session, current_user: Optional[User] = None) -> list:

    org = _org_id(current_user)
    proj_q = db.query(Project).filter(Project.status == ProjectStatus.active)
    if org:
        proj_q = proj_q.filter(Project.organization_id == org)
    projects = proj_q.all()
    if not projects:
        return []

    project_ids = [p.id for p in projects]
    today = timeutil.today()
    from app.core.umbrales import cortes as _cortes, tono_con
    cortes_presupuesto = _cortes("presupuesto", db, org)

    # Auditoría 22-11-2026 (§7.2): el coste del cálculo único en bloque.
    from app.services.margen_de_proyectos import margen_en_bloque
    cost_by_pid = {pid: c["total_cost"] for pid, c in margen_en_bloque(db, projects).items()}

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
    ).filter(Imputation.project_id.in_(project_ids), Imputation.is_active.is_(True)).group_by(Imputation.project_id).all()
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
            progress_pct, cortes_presupuesto,
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
            budget_tone=tono_con("presupuesto", budget_used_pct, *cortes_presupuesto),
        ))

    return result


# ── Resource load ──────────────────────────────────────────────────────────────

def get_resource_load(
    week_start: Optional[date],
    department: Optional[str],
    db: Session,
    current_user: Optional[User] = None,
) -> list:
    """Carga de cada persona en la semana. Auditoría 22-11-2026 (M8): consultas
    agregadas (antes cuatro por persona), solo imputaciones activas y, sin horas
    esta semana, la media de las cuatro anteriores marcada con `estimated`."""
    org = _org_id(current_user)
    if org is None and current_user is not None and not getattr(current_user, "is_superadmin", False):
        return []
    if not week_start:
        today = timeutil.today()
        week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    four_weeks_ago = week_start - timedelta(weeks=4)
    prev_week_end = week_start - timedelta(days=1)

    q = db.query(User).filter(User.is_active == True, User.status == UserStatus.active)
    if org:
        q = q.filter(User.organization_id == org)
    if department:
        q = q.filter(User.department == department)
    users = q.all()
    if not users:
        return []
    uids = [u.id for u in users]
    activa = Imputation.is_active.is_(True)

    def _suma(desde_, hasta_) -> dict:
        return dict(db.query(Imputation.user_id, func.sum(Imputation.hours)).filter(
            Imputation.user_id.in_(uids), activa, Imputation.date.between(desde_, hasta_),
        ).group_by(Imputation.user_id).all())

    semana = _suma(week_start, week_end)
    previas = _suma(four_weeks_ago, prev_week_end)
    proyectos = dict(db.query(Imputation.user_id, func.count(func.distinct(Imputation.project_id))).filter(
        Imputation.user_id.in_(uids), activa, Imputation.date >= week_start,
    ).group_by(Imputation.user_id).all())
    eficiencia = {r.user_id: r for r in db.query(
        Imputation.user_id,
        func.sum(Imputation.hours).label("real_h"),
        func.sum(Task.estimated_hours).label("est_h"),
    ).join(Task, Task.id == Imputation.task_id).filter(
        Imputation.user_id.in_(uids), activa,
        Task.status == TaskStatus.done,
        Task.estimated_hours > 0,
    ).group_by(Imputation.user_id).all()}

    result = []
    for user in users:
        hours_week = float(semana.get(user.id) or 0.0)
        estimada = False
        if hours_week == 0:
            hours_week = round(float(previas.get(user.id) or 0.0) / 4, 1)
            estimada = hours_week > 0
        capacity = capacidad_semanal(db, user)
        load_pct = round((hours_week / capacity) * 100, 1) if capacity else 0.0
        eff = eficiencia.get(user.id)
        efficiency = round(eff.est_h / eff.real_h, 2) if eff and eff.real_h and eff.est_h else 0.0
        result.append(ResourceLoadItem(
            user_id=user.id,
            user_name=user.full_name,
            department=user.department or "",
            load_pct=load_pct,
            hours_week=hours_week,
            active_projects=int(proyectos.get(user.id) or 0),
            efficiency=efficiency,
            estimated=estimada,
        ))

    return sorted(result, key=lambda x: x.load_pct, reverse=True)


# ── Profitability ──────────────────────────────────────────────────────────────

def get_profitability(
    date_from: Optional[date],
    date_to: Optional[date],
    db: Session,
    current_user: Optional[User] = None,
) -> list:
    """Rentabilidad por proyecto del panel.

    Auditoría 22-11-2026: (A25) sin empresa y sin ser superadmin, ninguna fila;
    (§7.2 / M8) las cifras son las del cálculo ÚNICO y en bloque
    (`margen_de_proyectos.margen_en_bloque`): personal convertido a la moneda de
    la empresa, gastos, subcontrata, licencias y equipos, ingreso por tarifas o
    hitos. Las mismas que rentabilidad, la evolución del margen, el EVM y el BI,
    con un número fijo de consultas sea cual sea el número de proyectos.
    """
    from app.services.margen_de_proyectos import margen_en_bloque
    org = _org_id(current_user)
    proj_q = db.query(Project).filter(
        Project.status.in_([ProjectStatus.active, ProjectStatus.closed])
    )
    if org:
        proj_q = proj_q.filter(Project.organization_id == org)
    elif current_user is not None and not getattr(current_user, "is_superadmin", False):
        return []
    projects = proj_q.all()
    cifras = margen_en_bloque(db, projects, date_from, date_to)

    result = []
    for p in projects:
        c = cifras[p.id]
        result.append({
            "project_id": p.id,
            "project_code": p.code,
            "project_name": p.name,
            "is_billable": p.is_billable,
            "budget_amount": p.budget_amount,
            "total_cost": c["total_cost"],
            "internal_cost": c["internal_cost"],
            "expenses_cost": c["expenses_cost"],
            "subcontract_cost": c["subcontract_cost"],
            "alm_cost": c["alm_cost"],
            "total_hours": c["hours"],
            "revenue": c["revenue"],
            "margin": c["margin"],
            "margin_pct": c["margin_pct"],
            "currency": c["currency"],
            "fx_warnings": c["fx_warnings"],
        })

    return sorted(result, key=lambda x: x["total_cost"], reverse=True)


# ── Team productivity ──────────────────────────────────────────────────────────

def get_team_productivity(
    date_from: Optional[date],
    date_to: Optional[date],
    department: Optional[str],
    db: Session,
    current_user: Optional[User] = None,
) -> dict:
    """Horas y tareas terminadas por persona EN EL PERIODO (auditoría 22-11-2026,
    M8: antes las tareas contaban de siempre y las horas incluían borradas; dos
    consultas por persona → dos agregadas)."""
    from datetime import datetime, time, timezone
    if not date_from:
        date_from = timeutil.today().replace(day=1)
    if not date_to:
        date_to = timeutil.today()

    org = _org_id(current_user)
    if org is None and current_user is not None and not getattr(current_user, "is_superadmin", False):
        return {"period_start": date_from, "period_end": date_to, "team_stats": []}
    q = db.query(User).filter(User.is_active == True)
    if org:
        q = q.filter(User.organization_id == org)
    if department:
        q = q.filter(User.department == department)
    users = q.all()
    uids = [u.id for u in users] or [""]

    horas = dict(db.query(Imputation.user_id, func.sum(Imputation.hours)).filter(
        Imputation.user_id.in_(uids), Imputation.is_active.is_(True),
        Imputation.date.between(date_from, date_to),
    ).group_by(Imputation.user_id).all())
    ini = datetime.combine(date_from, time.min, tzinfo=timezone.utc)
    fin = datetime.combine(date_to, time.max, tzinfo=timezone.utc)
    hechas = dict(db.query(Task.assignee_id, func.count(Task.id)).filter(
        Task.assignee_id.in_(uids), Task.status == TaskStatus.done,
        Task.completed_at.isnot(None), Task.completed_at >= ini, Task.completed_at <= fin,
    ).group_by(Task.assignee_id).all())

    result = [{
        "user_id": user.id,
        "user_name": user.full_name,
        "department": user.department,
        "job_title": user.job_title,
        "hours_logged": float(horas.get(user.id) or 0.0),
        "tasks_completed": int(hechas.get(user.id) or 0),
    } for user in users]

    return {"period_start": date_from, "period_end": date_to, "team_stats": result}
