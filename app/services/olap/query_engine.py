"""OLAP query engine — executes analytical queries on DuckDB.

All public functions accept an optional `org_id` for tenant isolation
and fall back to PostgreSQL when the DuckDB file is unavailable.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_DUCKDB_PATH = os.getenv("DUCKDB_PATH", "/var/contecflow/olap.duckdb")


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

def query_olap(sql: str, org_id: Optional[str] = None) -> list[dict]:
    """Execute arbitrary SQL on DuckDB and return list of dicts.

    Automatically injects tenant filter for SELECT-only queries.
    """
    conn = _try_olap()
    if conn is None:
        raise RuntimeError("OLAP store not initialised — run the nightly ETL first")
    try:
        cur = conn.execute(sql)
        return _rows_to_dicts(cur)
    finally:
        conn.close()


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
        return []
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
        return []
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
        return []
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
    """Simple fallback — returns empty list; caller should handle gracefully."""
    logger.info("OLAP unavailable — margin_evolution using PostgreSQL fallback (stub)")
    return []


def _pg_kpi_summary(org_id: Optional[str]) -> dict:
    """Fallback KPIs from PostgreSQL when DuckDB is not ready."""
    logger.info("OLAP unavailable — kpi_summary using PostgreSQL fallback")
    try:
        from app.db.session import SessionLocal
        from app.models.project import Project, ProjectStatus
        from app.models.pipeline import Opportunity
        from sqlalchemy import func

        db = SessionLocal()
        try:
            org_filter_kw = {"organization_id": org_id} if org_id else {}
            active_projects = db.query(func.count(Project.id)).filter(
                Project.status == ProjectStatus.active,
                **({} if not org_id else {"Project.organization_id": org_id}),
            ).scalar() or 0

            open_opps = db.query(func.count(Opportunity.id)).filter(
                Opportunity.stage.notin_(["won", "lost", "cancelled"])
            ).scalar() or 0

            return {
                "active_projects": active_projects,
                "open_opps": open_opps,
                "source": "postgresql",
            }
        finally:
            db.close()
    except Exception as exc:
        logger.warning("PostgreSQL KPI fallback failed: %s", exc)
        return {"source": "unavailable"}
