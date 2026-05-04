"""ETL: PostgreSQL → DuckDB OLAP store.

Entry points:
    run_full_etl(db, since=None)   — incremental by default (last 2 days)
    get_duckdb_conn()              — returns an open DuckDB connection
"""
from __future__ import annotations

import logging
import os
from datetime import date, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

from app.core.config import settings() -> str:
    env_path = os.getenv("DUCKDB_PATH")
    if env_path:
        return env_path

    preferred = "/var/contecflow/olap.duckdb"
    preferred_dir = os.path.dirname(preferred)
    try:
        os.makedirs(preferred_dir, exist_ok=True)
        if os.access(preferred_dir, os.W_OK):
            return preferred
    except Exception:
        pass

    # Local/dev fallback when /var is not writable (common on macOS without root).
    fallback = "/tmp/contecflow/olap.duckdb"
    os.makedirs(os.path.dirname(fallback), exist_ok=True)
    return fallback


DUCKDB_PATH = _resolve_duckdb_path()


def get_duckdb_conn():
    """Return an open DuckDB connection, initialising schema if needed."""
    try:
        import duckdb
    except ImportError:
        raise RuntimeError("duckdb not installed — run: pip install duckdb==1.3.0")

    os.makedirs(os.path.dirname(DUCKDB_PATH), exist_ok=True)
    conn = duckdb.connect(DUCKDB_PATH)
    from app.services.olap.schema import initialize_schema
    initialize_schema(conn)
    return conn


# ── Dimension helpers ─────────────────────────────────────────────────────────

def _date_key(d: Optional[date]) -> Optional[int]:
    return int(d.strftime("%Y%m%d")) if d else None


def _ensure_dim_date(conn, dates: list[date]) -> None:
    for d in set(dates):
        if d is None:
            continue
        key = _date_key(d)
        conn.execute("""
            INSERT OR REPLACE INTO dim_date VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            key, d, d.year, (d.month - 1) // 3 + 1, d.month,
            d.strftime("%B"), d.isocalendar()[1], d.weekday(),
            d.weekday() >= 5, d.strftime("%Y-%m"),
        ])


# ── Loaders ───────────────────────────────────────────────────────────────────

def _load_dim_organizations(db, conn) -> None:
    from app.models.mfa import Organization
    rows = db.query(Organization).all()
    for o in rows:
        conn.execute("""
            INSERT OR REPLACE INTO dim_organization VALUES (?, ?, ?)
        """, [o.id, getattr(o, "name", None), getattr(o, "plan", None)])
    logger.debug("dim_organization: %d rows", len(rows))


def _load_dim_clients(db, conn) -> None:
    from app.models.clients import Client
    rows = db.query(Client).all()
    for c in rows:
        conn.execute("""
            INSERT OR REPLACE INTO dim_client VALUES (?, ?, ?, ?)
        """, [c.id, c.name,
              getattr(c, "industry", None),
              getattr(c, "organization_id", None)])
    logger.debug("dim_client: %d rows", len(rows))


def _load_dim_users(db, conn) -> None:
    from app.models.user import User
    rows = db.query(User).filter(User.is_active.is_(True)).all()
    for u in rows:
        conn.execute("""
            INSERT OR REPLACE INTO dim_user VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            u.id,
            u.full_name,
            u.email,
            u.role.value if hasattr(u.role, "value") else str(u.role),
            getattr(u, "department", None),
            getattr(u, "organization_id", None),
            getattr(u, "cost_per_hour", None),
            getattr(u, "weekly_capacity_hours", settings.DEFAULT_WEEKLY_CAPACITY_HOURS),
        ])
    logger.debug("dim_user: %d rows", len(rows))


def _load_dim_projects(db, conn) -> None:
    from app.models.project import Project
    rows = db.query(Project).all()
    for p in rows:
        conn.execute("""
            INSERT OR REPLACE INTO dim_project VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            p.id, p.code, p.name,
            p.status.value if hasattr(p.status, "value") else str(p.status),
            p.project_type.value if hasattr(p.project_type, "value") else str(p.project_type),
            getattr(p, "billing_type", None),
            getattr(p, "organization_id", None),
            getattr(p, "client_id", None),
            p.start_date, p.end_date,
            getattr(p, "budget", None),
            getattr(p, "currency", settings.DEFAULT_CURRENCY),
        ])
    logger.debug("dim_project: %d rows", len(rows))


def _load_fact_imputations(db, conn, since: date) -> int:
    from app.models.imputation import Imputation
    from app.models.project import Project
    rows = (
        db.query(Imputation)
        .filter(Imputation.date >= since)
        .all()
    )
    dates = [r.date for r in rows]
    _ensure_dim_date(conn, dates)

    loaded = 0
    for imp in rows:
        cost_ph = None
        try:
            from app.models.user import User
            u = db.query(User).filter(User.id == imp.user_id).first()
            cost_ph = getattr(u, "cost_per_hour", None)
        except Exception:
            pass
        cost = (imp.hours or 0) * (cost_ph or 0)

        project_org = None
        try:
            proj = db.query(Project).filter(Project.id == imp.project_id).first()
            project_org = getattr(proj, "organization_id", None) if proj else None
        except Exception:
            pass

        conn.execute("""
            INSERT OR REPLACE INTO fact_imputations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            imp.id,
            _date_key(imp.date),
            imp.project_id,
            imp.user_id,
            project_org,
            imp.hours or 0,
            imp.hours if getattr(imp, "is_billable", False) else 0.0,
            cost,
            getattr(imp, "is_billable", False),
            getattr(imp, "task_id", None),
        ])
        loaded += 1

    logger.debug("fact_imputations: %d rows (since %s)", loaded, since)
    return loaded


def _load_fact_projects(db, conn) -> int:
    from app.models.project import Project
    from app.models.imputation import Imputation
    from app.models.financial import ProjectMilestone
    from app.models.task import Task, TaskStatus
    from sqlalchemy import func

    rows = db.query(Project).all()
    loaded = 0
    for p in rows:
        total_hours = db.query(func.sum(Imputation.hours)).filter(
            Imputation.project_id == p.id
        ).scalar() or 0.0

        cost_ph_subq = db.query(Imputation, func.sum(Imputation.hours)).filter(
            Imputation.project_id == p.id
        ).all()
        total_cost = 0.0
        for imp, _ in cost_ph_subq:
            from app.models.user import User
            u = db.query(User).filter(User.id == imp.user_id).first()
            cph = getattr(u, "cost_per_hour", 0) or 0
            total_cost += (imp.hours or 0) * cph

        budget = getattr(p, "budget", 0) or 0
        revenue = getattr(p, "billing_amount", 0) or budget
        margin = revenue - total_cost
        margin_pct = round(margin / revenue * 100, 1) if revenue else 0

        tasks_total = db.query(func.count(Task.id)).filter(Task.project_id == p.id).scalar() or 0
        tasks_done = db.query(func.count(Task.id)).filter(
            Task.project_id == p.id, Task.status == TaskStatus.done
        ).scalar() or 0

        miles_total = db.query(func.count(ProjectMilestone.id)).filter(
            ProjectMilestone.project_id == p.id
        ).scalar() or 0
        miles_done = db.query(func.count(ProjectMilestone.id)).filter(
            ProjectMilestone.project_id == p.id,
            ProjectMilestone.is_completed.is_(True),
        ).scalar() or 0

        risk = p.risk
        risk_str = risk.value if hasattr(risk, "value") else str(risk) if risk else None
        status_str = p.status.value if hasattr(p.status, "value") else str(p.status)

        conn.execute("""
            INSERT OR REPLACE INTO fact_projects VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            p.id,
            getattr(p, "organization_id", None),
            _date_key(p.start_date),
            _date_key(p.end_date),
            budget,
            total_hours,
            total_cost,
            revenue,
            margin,
            margin_pct,
            tasks_total,
            tasks_done,
            miles_total,
            miles_done,
            risk_str,
            status_str,
        ])
        loaded += 1

    logger.debug("fact_projects: %d rows", loaded)
    return loaded


def _load_fact_pipeline(db, conn) -> int:
    from app.models.pipeline import Opportunity
    from datetime import datetime, timezone

    rows = db.query(Opportunity).all()
    dates: list[date] = []
    for o in rows:
        if o.expected_close_date:
            dates.append(o.expected_close_date)
        if o.created_at:
            dates.append(o.created_at.date() if hasattr(o.created_at, "date") else o.created_at)
    _ensure_dim_date(conn, dates)

    loaded = 0
    for o in rows:
        created_date = (
            o.created_at.date() if hasattr(o.created_at, "date") else o.created_at
        ) if o.created_at else None
        days_in = (date.today() - created_date).days if created_date else None

        conn.execute("""
            INSERT OR REPLACE INTO fact_pipeline VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            o.id,
            getattr(o, "organization_id", None),
            o.stage,
            o.expected_revenue or 0,
            o.probability or 0,
            (o.expected_revenue or 0) * (o.probability or 0) / 100,
            _date_key(o.expected_close_date),
            _date_key(created_date),
            getattr(o, "client_id", None),
            getattr(o, "owner_id", None),
            getattr(o, "contract_type", None),
            o.stage == "won",
            o.stage == "lost",
            days_in,
        ])
        loaded += 1

    logger.debug("fact_pipeline: %d rows", loaded)
    return loaded


def _load_fact_tickets(db, conn) -> int:
    from app.models.service_desk import Ticket

    rows = db.query(Ticket).all()
    dates: list[date] = []
    for t in rows:
        if t.created_at:
            d = t.created_at.date() if hasattr(t.created_at, "date") else t.created_at
            dates.append(d)
        closed = getattr(t, "closed_at", None) or getattr(t, "resolved_at", None)
        if closed:
            d2 = closed.date() if hasattr(closed, "date") else closed
            dates.append(d2)
    _ensure_dim_date(conn, dates)

    loaded = 0
    for t in rows:
        created_date = (
            t.created_at.date() if hasattr(t.created_at, "date") else t.created_at
        ) if t.created_at else None
        closed_raw = getattr(t, "closed_at", None) or getattr(t, "resolved_at", None)
        closed_date = (
            closed_raw.date() if hasattr(closed_raw, "date") else closed_raw
        ) if closed_raw else None

        resolution_hours = None
        if created_date and closed_date:
            resolution_hours = (closed_date - created_date).days * 24.0

        sla_breached = getattr(t, "sla_breached", False) or getattr(t, "sla_status", None) == "breached"

        conn.execute("""
            INSERT OR REPLACE INTO fact_tickets VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            t.id,
            getattr(t, "organization_id", None),
            _date_key(created_date),
            _date_key(closed_date),
            t.status.value if hasattr(t.status, "value") else str(t.status),
            t.priority.value if hasattr(t.priority, "value") else str(t.priority),
            t.ticket_type.value if hasattr(t.ticket_type, "value") else str(t.ticket_type),
            getattr(t, "category_id", None),
            getattr(t, "assigned_agent_id", None),
            getattr(t, "client_id", None),
            resolution_hours,
            bool(sla_breached),
            getattr(t, "satisfaction_score", None),
        ])
        loaded += 1

    logger.debug("fact_tickets: %d rows", loaded)
    return loaded


# ── Public API ────────────────────────────────────────────────────────────────

def run_full_etl(db, since: Optional[date] = None) -> dict:
    """Run incremental ETL from PostgreSQL to DuckDB.

    Args:
        db:    SQLAlchemy session.
        since: Load imputations from this date forward.
               Defaults to today - 2 days (incremental).
               Pass date(2023, 1, 1) for a full historical load.
    """
    if since is None:
        since = date.today() - timedelta(days=2)

    conn = get_duckdb_conn()
    try:
        logger.info("OLAP ETL start (since=%s)", since)

        _load_dim_organizations(db, conn)
        _load_dim_clients(db, conn)
        _load_dim_users(db, conn)
        _load_dim_projects(db, conn)

        imp_count = _load_fact_imputations(db, conn, since)
        proj_count = _load_fact_projects(db, conn)
        pipe_count = _load_fact_pipeline(db, conn)
        tick_count = _load_fact_tickets(db, conn)

        conn.commit()
        result = {
            "status": "ok",
            "since": str(since),
            "imputations": imp_count,
            "projects": proj_count,
            "pipeline": pipe_count,
            "tickets": tick_count,
        }
        logger.info("OLAP ETL complete: %s", result)
        return result
    except Exception as exc:
        logger.error("OLAP ETL failed: %s", exc, exc_info=True)
        raise
    finally:
        conn.close()
