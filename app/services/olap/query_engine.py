"""OLAP query engine — executes analytical queries on DuckDB.

All public functions accept an optional `org_id` for tenant isolation
and fall back to PostgreSQL when the DuckDB file is unavailable.
"""
from __future__ import annotations

import logging
import os
from typing import Optional
from app.services.olap.etl import DUCKDB_PATH as _DUCKDB_PATH

logger = logging.getLogger(__name__)

def _olap_available() -> bool:
    return os.path.exists(_DUCKDB_PATH)


def _try_olap():
    """Return an open DuckDB connection or None if unavailable."""
    if not _olap_available():
        return None
    try:
        from app.services.olap.etl import get_duckdb_conn
        return get_duckdb_conn()
    except Exception as exc:
        logger.warning("DuckDB unavailable, falling back to PostgreSQL: %s", exc)
        return None


def _rows_to_dicts(cursor) -> list[dict]:
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def _org_filter(org_id: Optional[str], table_alias: str = "") -> str:
    prefix = f"{table_alias}." if table_alias else ""
    if org_id:
        return f"AND {prefix}organization_id = '{org_id}'"
    return ""


# ── Public query functions ────────────────────────────────────────────────────

def get_margin_evolution(org_id: Optional[str] = None, months: int = 12) -> list[dict]:
    """Monthly margin evolution for all projects."""
    conn = _try_olap()
    if conn is None:
        return _pg_margin_evolution(org_id, months)
    try:
        sql = f"""
        SELECT
            d.yyyymm                        AS month,
            ROUND(SUM(fi.cost), 2)          AS total_cost,
            COUNT(DISTINCT fi.project_id)   AS active_projects
        FROM fact_imputations fi
        JOIN dim_date d ON d.date_key = fi.date_key
        WHERE d.date >= (CURRENT_DATE - INTERVAL '{months} months')
        {_org_filter(org_id, 'fi')}
        GROUP BY d.yyyymm
        ORDER BY d.yyyymm
        """
        cur = conn.execute(sql)
        return _rows_to_dicts(cur)
    finally:
        conn.close()


def get_utilization_by_user(
    org_id: Optional[str] = None,
    since_key: Optional[int] = None,
    until_key: Optional[int] = None,
) -> list[dict]:
    """Actual vs capacity utilisation per user."""
    conn = _try_olap()
    if conn is None:
        return _pg_utilization_by_user(org_id)
    try:
        date_filter = ""
        if since_key:
            date_filter += f" AND fi.date_key >= {since_key}"
        if until_key:
            date_filter += f" AND fi.date_key <= {until_key}"

        sql = f"""
        SELECT
            u.user_id,
            u.full_name,
            u.department,
            ROUND(SUM(fi.hours), 1)                     AS logged_hours,
            ROUND(u.weekly_capacity * 52 / 12, 1)       AS monthly_capacity,
            ROUND(SUM(fi.hours) / NULLIF(u.weekly_capacity * 52 / 12, 0) * 100, 1) AS utilization_pct
        FROM fact_imputations fi
        JOIN dim_user u ON u.user_id = fi.user_id
        WHERE 1=1
        {date_filter}
        {_org_filter(org_id, 'fi')}
        GROUP BY u.user_id, u.full_name, u.department, u.weekly_capacity
        ORDER BY utilization_pct DESC
        """
        cur = conn.execute(sql)
        return _rows_to_dicts(cur)
    finally:
        conn.close()


def get_portfolio_health(org_id: Optional[str] = None) -> list[dict]:
    """Project health snapshot: margin%, task completion%, risk level."""
    conn = _try_olap()
    if conn is None:
        return _pg_portfolio_health(org_id)
    try:
        org_f = _org_filter(org_id)
        sql = f"""
        SELECT
            fp.project_id,
            dp.code,
            dp.name,
            dp.status,
            fp.budget,
            fp.total_cost,
            fp.margin_pct,
            fp.tasks_total,
            fp.tasks_done,
            ROUND(fp.tasks_done * 100.0 / NULLIF(fp.tasks_total, 0), 1) AS completion_pct,
            fp.milestones_done,
            fp.milestones_total,
            fp.risk_level
        FROM fact_projects fp
        JOIN dim_project dp ON dp.project_id = fp.project_id
        WHERE dp.status NOT IN ('cancelled', 'archived')
        {org_f}
        ORDER BY fp.margin_pct ASC
        """
        cur = conn.execute(sql)
        return _rows_to_dicts(cur)
    finally:
        conn.close()


def get_pipeline_funnel(org_id: Optional[str] = None) -> list[dict]:
    """Pipeline funnel: count and weighted revenue by stage."""
    conn = _try_olap()
    if conn is None:
        return _pg_pipeline_funnel(org_id)
    try:
        org_f = _org_filter(org_id)
        sql = f"""
        SELECT
            stage,
            COUNT(*)                            AS count,
            ROUND(SUM(expected_revenue), 0)     AS total_revenue,
            ROUND(SUM(weighted_revenue), 0)     AS weighted_revenue,
            ROUND(AVG(probability), 1)          AS avg_probability,
            ROUND(AVG(days_in_pipeline), 0)     AS avg_days
        FROM fact_pipeline
        WHERE NOT is_lost AND NOT is_won
        {org_f}
        GROUP BY stage
        ORDER BY
            CASE stage
                WHEN 'lead' THEN 1
                WHEN 'qualification' THEN 2
                WHEN 'proposal' THEN 3
                WHEN 'negotiation' THEN 4
                ELSE 5
            END
        """
        cur = conn.execute(sql)
        return _rows_to_dicts(cur)
    finally:
        conn.close()


def get_kpi_summary(org_id: Optional[str] = None) -> dict:
    """Top-level KPIs for storytelling and dashboard summary."""
    conn = _try_olap()
    if conn is None:
        return _pg_kpi_summary(org_id)
    try:
        org_f_bare = f"organization_id = '{org_id}'" if org_id else "1=1"

        # Current month
        imp_sql = f"""
        SELECT
            ROUND(SUM(hours), 1)            AS hours_mtd,
            ROUND(SUM(cost), 0)             AS cost_mtd,
            COUNT(DISTINCT project_id)      AS active_projects_mtd,
            ROUND(SUM(billable_hours) * 100.0 / NULLIF(SUM(hours),0), 1) AS billability_pct
        FROM fact_imputations fi
        JOIN dim_date d ON d.date_key = fi.date_key
        WHERE d.yyyymm = strftime(CURRENT_DATE, '%Y-%m')
        AND {org_f_bare.replace('organization_id', 'fi.organization_id')}
        """
        cur = conn.execute(imp_sql)
        imp = (_rows_to_dicts(cur) or [{}])[0]

        pipe_sql = f"""
        SELECT
            COUNT(*) FILTER (WHERE NOT is_won AND NOT is_lost) AS open_opps,
            ROUND(SUM(weighted_revenue) FILTER (WHERE NOT is_won AND NOT is_lost), 0) AS pipeline_weighted,
            ROUND(SUM(expected_revenue) FILTER (WHERE is_won), 0) AS won_revenue
        FROM fact_pipeline
        WHERE {org_f_bare}
        """
        cur2 = conn.execute(pipe_sql)
        pipe = (_rows_to_dicts(cur2) or [{}])[0]

        proj_sql = f"""
        SELECT
            COUNT(*) FILTER (WHERE status = 'active')      AS active_projects,
            ROUND(AVG(margin_pct) FILTER (WHERE status = 'active'), 1) AS avg_margin_pct,
            COUNT(*) FILTER (WHERE risk_level = 'high')    AS high_risk_projects
        FROM fact_projects
        WHERE {org_f_bare}
        """
        cur3 = conn.execute(proj_sql)
        proj = (_rows_to_dicts(cur3) or [{}])[0]

        return {**imp, **pipe, **proj, "source": "olap"}
    finally:
        conn.close()


# ── PostgreSQL fallbacks ──────────────────────────────────────────────────────

def _pg_margin_evolution(org_id: Optional[str], months: int) -> list[dict]:
    """Monthly cost + active-project count from PostgreSQL when DuckDB is not
    ready. Aggregates in Python so it works on both Postgres and SQLite, and
    excludes soft-deleted imputations to match the financial aggregates."""
    logger.info("OLAP unavailable — margin_evolution using PostgreSQL fallback")
    try:
        from app.db.session import SessionLocal
        from app.models.imputation import Imputation
        from app.models.project import Project
        from datetime import date

        today = date.today()
        # First day of the month, `months` months back.
        start_year = today.year + (today.month - 1 - (months - 1)) // 12
        start_month = (today.month - 1 - (months - 1)) % 12 + 1
        window_start = date(start_year, start_month, 1)

        db = SessionLocal()
        try:
            q = (
                db.query(Imputation.date, Imputation.cost_amount, Imputation.project_id)
                .filter(Imputation.date >= window_start, Imputation.is_active == True)
            )
            if org_id:
                proj_ids = [p.id for p in db.query(Project.id).filter(Project.organization_id == org_id).all()]
                q = q.filter(Imputation.project_id.in_(proj_ids))

            buckets: dict[str, dict] = {}
            for imp_date, cost_amount, project_id in q.all():
                key = f"{imp_date.year:04d}{imp_date.month:02d}"
                b = buckets.setdefault(key, {"month": key, "total_cost": 0.0, "_projects": set()})
                b["total_cost"] += float(cost_amount or 0)
                if project_id:
                    b["_projects"].add(project_id)

            result = []
            for key in sorted(buckets):
                b = buckets[key]
                result.append({
                    "month": b["month"],
                    "total_cost": round(b["total_cost"], 2),
                    "active_projects": len(b["_projects"]),
                })
            return result
        finally:
            db.close()
    except Exception as exc:
        logger.warning("PostgreSQL margin_evolution fallback failed: %s", exc)
        return []


def _pg_utilization_by_user(org_id: Optional[str]) -> list[dict]:
    """Utilization per user from PostgreSQL when DuckDB is not ready."""
    logger.info("OLAP unavailable — utilization_by_user using PostgreSQL fallback")
    try:
        from app.db.session import SessionLocal
        from app.models.user import User
        from app.models.imputation import Imputation
        from app.models.resources import Resource
        from sqlalchemy import func
        from datetime import date

        db = SessionLocal()
        try:
            today = date.today()
            month_start = today.replace(day=1)

            query = (
                db.query(
                    User.id.label("user_id"),
                    func.concat(User.first_name, " ", User.last_name).label("full_name"),
                    User.department.label("department"),
                    func.round(func.sum(Imputation.hours), 1).label("logged_hours"),
                )
                .join(Imputation, Imputation.user_id == User.id)
                .filter(
                    Imputation.date >= month_start,
                    Imputation.date <= today,
                )
            )
            if org_id:
                query = query.filter(User.organization_id == org_id)
            rows = query.group_by(User.id, User.first_name, User.last_name, User.department).all()

            result = []
            for r in rows:
                resource = db.query(Resource).filter(Resource.user_id == r.user_id).first()
                weekly_capacity = float(getattr(resource, "weekly_capacity", 40) or 40)
                monthly_capacity = round(weekly_capacity * 52 / 12, 1)
                logged = float(r.logged_hours or 0)
                utilization_pct = round(logged / monthly_capacity * 100, 1) if monthly_capacity else 0.0
                result.append({
                    "user_id": r.user_id,
                    "full_name": r.full_name,
                    "department": r.department,
                    "logged_hours": logged,
                    "monthly_capacity": monthly_capacity,
                    "utilization_pct": utilization_pct,
                })
            result.sort(key=lambda x: x["utilization_pct"], reverse=True)
            return result
        finally:
            db.close()
    except Exception as exc:
        logger.warning("PostgreSQL utilization fallback failed: %s", exc)
        return []


def _pg_pipeline_funnel(org_id: Optional[str]) -> list[dict]:
    """Pipeline funnel from PostgreSQL when DuckDB is not ready."""
    logger.info("OLAP unavailable — pipeline_funnel using PostgreSQL fallback")
    try:
        from app.db.session import SessionLocal
        from app.models.pipeline import Opportunity
        from sqlalchemy import func

        db = SessionLocal()
        try:
            STAGE_ORDER = {"lead": 1, "qualification": 2, "proposal": 3, "negotiation": 4}
            filters = [Opportunity.stage.notin_(["won", "lost", "cancelled"])]
            if org_id:
                filters.append(Opportunity.organization_id == org_id)

            rows = (
                db.query(
                    Opportunity.stage.label("stage"),
                    func.count(Opportunity.id).label("count"),
                    func.round(func.sum(Opportunity.expected_revenue), 0).label("total_revenue"),
                    func.round(
                        func.sum(
                            Opportunity.expected_revenue
                            * func.coalesce(Opportunity.probability, 0.0)
                            / 100.0
                        ),
                        0,
                    ).label("weighted_revenue"),
                    func.round(func.avg(Opportunity.probability), 1).label("avg_probability"),
                )
                .filter(*filters)
                .group_by(Opportunity.stage)
                .all()
            )

            result = [
                {
                    "stage": r.stage,
                    "count": int(r.count or 0),
                    "total_revenue": float(r.total_revenue or 0),
                    "weighted_revenue": float(r.weighted_revenue or 0),
                    "avg_probability": float(r.avg_probability or 0),
                    "avg_days": None,
                }
                for r in rows
            ]
            result.sort(key=lambda x: STAGE_ORDER.get(x["stage"], 99))
            return result
        finally:
            db.close()
    except Exception as exc:
        logger.warning("PostgreSQL pipeline fallback failed: %s", exc)
        return []


def _pg_portfolio_health(org_id: Optional[str]) -> list[dict]:
    """Portfolio health from PostgreSQL when DuckDB is not ready."""
    logger.info("OLAP unavailable — portfolio_health using PostgreSQL fallback")
    try:
        from app.db.session import SessionLocal
        from app.models.project import Project
        from app.models.task import Task
        from app.models.imputation import Imputation
        from sqlalchemy import func

        db = SessionLocal()
        try:
            filters = [Project.status.notin_(["cancelled", "archived"])]
            if org_id:
                filters.append(Project.organization_id == org_id)

            projects = db.query(Project).filter(*filters).all()
            result = []
            for proj in projects:
                tasks_total = db.query(func.count(Task.id)).filter(Task.project_id == proj.id).scalar() or 0
                tasks_done = (
                    db.query(func.count(Task.id))
                    .filter(Task.project_id == proj.id, Task.status == "done")
                    .scalar() or 0
                )
                completion_pct = round(tasks_done / tasks_total * 100, 1) if tasks_total else 0.0

                total_cost = (
                    db.query(func.sum(Imputation.cost_amount))
                    .filter(Imputation.project_id == proj.id)
                    .scalar() or 0.0
                )
                budget = float(proj.budget_amount or 0)
                if budget > 0:
                    revenue_est = budget
                    margin_pct = round((revenue_est - float(total_cost)) / revenue_est * 100, 1)
                else:
                    margin_pct = 0.0

                result.append({
                    "project_id": proj.id,
                    "code": proj.code,
                    "name": proj.name,
                    "status": proj.status.value if hasattr(proj.status, "value") else str(proj.status),
                    "budget": budget,
                    "total_cost": float(total_cost),
                    "margin_pct": margin_pct,
                    "tasks_total": tasks_total,
                    "tasks_done": tasks_done,
                    "completion_pct": completion_pct,
                    "risk_level": proj.risk_level.value if hasattr(proj.risk_level, "value") else str(proj.risk_level or "low"),
                })
            result.sort(key=lambda x: x["margin_pct"])
            return result
        finally:
            db.close()
    except Exception as exc:
        logger.warning("PostgreSQL portfolio fallback failed: %s", exc)
        return []


def _pg_kpi_summary(org_id: Optional[str]) -> dict:
    """Fallback KPIs from PostgreSQL when DuckDB is not ready."""
    logger.info("OLAP unavailable — kpi_summary using PostgreSQL fallback")
    try:
        from app.db.session import SessionLocal
        from app.models.project import Project, ProjectStatus, ProjectRisk
        from app.models.pipeline import Opportunity
        from app.models.imputation import Imputation
        from sqlalchemy import case, false, func
        from datetime import date

        db = SessionLocal()
        try:
            proj_filters = [Project.status == ProjectStatus.active]
            if org_id:
                proj_filters.append(Project.organization_id == org_id)

            active_project_ids = [
                p.id for p in db.query(Project.id).filter(*proj_filters).all()
            ]
            active_projects = len(active_project_ids)

            high_risk_filters = [
                Project.status == ProjectStatus.active,
                Project.risk_level == ProjectRisk.high,
            ]
            if org_id:
                high_risk_filters.append(Project.organization_id == org_id)
            high_risk_projects = db.query(func.count(Project.id)).filter(*high_risk_filters).scalar() or 0

            avg_margin_pct = 0.0
            if active_project_ids:
                margin_rows = (
                    db.query(
                        Imputation.project_id.label("project_id"),
                        func.sum(Imputation.hours * func.coalesce(Project.billing_rate, 0.0)).label("revenue"),
                        func.sum(Imputation.cost_amount).label("cost"),
                    )
                    .join(Project, Project.id == Imputation.project_id)
                    .filter(Imputation.project_id.in_(active_project_ids))
                    .group_by(Imputation.project_id)
                    .all()
                )

                per_project_margins = []
                for row in margin_rows:
                    revenue = float(row.revenue or 0.0)
                    cost = float(row.cost or 0.0)
                    margin_pct = ((revenue - cost) / revenue * 100.0) if revenue > 0 else 0.0
                    per_project_margins.append(margin_pct)

                if per_project_margins:
                    avg_margin_pct = round(sum(per_project_margins) / len(per_project_margins), 1)

            opp_filters = [Opportunity.stage.notin_(["won", "lost", "cancelled"])]
            if org_id:
                opp_filters.append(Opportunity.organization_id == org_id)
            open_opps = db.query(func.count(Opportunity.id)).filter(*opp_filters).scalar() or 0

            weighted_expr = Opportunity.expected_revenue * (func.coalesce(Opportunity.probability, 0.0) / 100.0)
            pipeline_weighted = db.query(func.round(func.sum(weighted_expr), 0)).filter(*opp_filters).scalar() or 0

            won_filters = [Opportunity.stage == "won"]
            if org_id:
                won_filters.append(Opportunity.organization_id == org_id)
            won_revenue = db.query(func.round(func.sum(Opportunity.expected_revenue), 0)).filter(*won_filters).scalar() or 0

            today = date.today()
            month_start = today.replace(day=1)
            imp_filters = [Imputation.date >= month_start, Imputation.date <= today]
            if active_project_ids:
                imp_filters.append(Imputation.project_id.in_(active_project_ids))
            else:
                imp_filters.append(false())

            imp_row = db.query(
                func.round(func.sum(Imputation.hours), 1).label("hours_mtd"),
                func.round(func.sum(Imputation.cost_amount), 0).label("cost_mtd"),
                func.count(func.distinct(Imputation.project_id)).label("active_projects_mtd"),
                func.round(
                    func.sum(
                        case(
                            (Imputation.is_billable.is_(True), Imputation.hours),
                            else_=0.0,
                        )
                    )
                    * 100.0
                    / func.nullif(func.sum(Imputation.hours), 0.0),
                    1,
                ).label("billability_pct"),
            ).filter(*imp_filters).one()

            return {
                "hours_mtd": float(imp_row.hours_mtd or 0.0),
                "cost_mtd": float(imp_row.cost_mtd or 0.0),
                "active_projects_mtd": int(imp_row.active_projects_mtd or 0),
                "billability_pct": float(imp_row.billability_pct or 0.0),
                "active_projects": active_projects,
                "avg_margin_pct": avg_margin_pct,
                "high_risk_projects": int(high_risk_projects),
                "open_opps": int(open_opps),
                "pipeline_weighted": float(pipeline_weighted or 0.0),
                "won_revenue": float(won_revenue or 0.0),
                "source": "postgresql",
            }
        finally:
            db.close()
    except Exception as exc:
        logger.warning("PostgreSQL KPI fallback failed: %s", exc)
        return {"source": "unavailable"}
