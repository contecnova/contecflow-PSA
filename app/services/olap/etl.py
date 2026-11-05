"""ETL: PostgreSQL → DuckDB OLAP store.

Entry points:
    run_full_etl(db, since=None)   — full reload by default (revisión 2026-11)
    get_duckdb_conn()              — returns an open DuckDB connection
"""
from __future__ import annotations

import logging
import os
from datetime import date, datetime
from typing import Optional
from app.core import timeutil

logger = logging.getLogger(__name__)

from app.core.config import settings


def _resolve_duckdb_path() -> str:
    env_path = os.getenv("DUCKDB_PATH")
    if env_path:
        return env_path

    preferred = "/var/contecflow/olap.duckdb"
    preferred_dir = os.path.dirname(preferred)
    try:
        os.makedirs(preferred_dir, exist_ok=True)
        if os.access(preferred_dir, os.W_OK):
            return preferred
    # intentional: best-effort fallback, log noise outweighs diagnostic value
    except Exception:
        logger.debug("_resolve_duckdb_path: fallo best-effort ignorado", exc_info=True)

    # Local/dev fallback when /var is not writable (common on macOS without root).
    fallback = "/tmp/contecflow/olap.duckdb"  # noqa: S108
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
#
# Revisión 2026-11. La carga reventaba en `_load_dim_projects` (`Project.end_date`
# no existe) y, corregido eso, en `_load_fact_projects` (Postgres rechazaba
# `query(Imputation, func.sum(...))` sin GROUP BY): el almacén estaba vacío y
# Ask-the-Data contestaba sobre nada. Además, muchos campos se leían con
# `getattr(obj, "campo", defecto)` y no existían (`budget`, `billing_amount`,
# `risk`, `cost_per_hour`, `sla_breached`, `category_id`, `assigned_agent_id`,
# `satisfaction_score`): se cargaban vacíos sin avisar. Ahora cada campo se lee
# por su atributo real, para que un nombre que falte rompa en vez de mentir.
#
# Y es una recarga COMPLETA dentro de una transacción: con `INSERT OR REPLACE`
# lo borrado en Postgres (p. ej. por retención) se quedaba para siempre aquí.

def _valor(v):
    return v.value if hasattr(v, "value") else (str(v) if v is not None else None)


def _dia(v) -> Optional[date]:
    """El día de una fecha u hora (las horas se guardan con zona; el día es el de UTC)."""
    return v.date() if isinstance(v, datetime) else v


def _vaciar_y_cargar(conn, tabla: str, columnas: int, filas: list[list]) -> int:
    conn.execute(f"DELETE FROM {tabla}")  # noqa: S608 — tabla fija del esquema
    if filas:
        conn.executemany(f"INSERT INTO {tabla} VALUES ({', '.join('?' * columnas)})", filas)  # noqa: S608
    return len(filas)


def _load_dim_organizations(db, conn) -> int:
    from app.models.mfa import Organization
    return _vaciar_y_cargar(conn, "dim_organization", 3,
                            [[o.id, o.name, o.plan] for o in db.query(Organization).all()])


def _load_dim_clients(db, conn) -> int:
    from app.models.clients import Client
    return _vaciar_y_cargar(conn, "dim_client", 4,
                            [[c.id, c.name, c.industry, c.organization_id] for c in db.query(Client).all()])


def _load_dim_users(db, conn) -> int:
    from app.models.user import User
    filas = [[u.id, u.full_name, u.email, _valor(u.role), u.department, u.organization_id,
              u.hourly_rate,   # coste interno €/h (User.hourly_rate)
              u.weekly_capacity_hours if u.weekly_capacity_hours is not None
              else settings.DEFAULT_WEEKLY_CAPACITY_HOURS]
             for u in db.query(User).filter(User.is_active.is_(True)).all()]
    return _vaciar_y_cargar(conn, "dim_user", 8, filas)


def _load_dim_projects(db, conn) -> int:
    from app.models.project import Project
    filas = [[p.id, p.code, p.name, _valor(p.status), _valor(p.project_type), p.billing_type, p.organization_id,
              p.client_id, p.start_date, p.end_date_real or p.end_date_planned, p.budget_amount,
              p.currency or settings.DEFAULT_CURRENCY]
             for p in db.query(Project).all()]
    return _vaciar_y_cargar(conn, "dim_project", 12, filas)


def _coste_de(imp, tarifa_usuario: dict) -> float:
    """Lo que la imputación guardó (`cost_amount`); si no, horas × tarifa de entonces o la actual."""
    if imp.cost_amount is not None:
        return float(imp.cost_amount)
    tarifa = imp.hourly_rate_snapshot if imp.hourly_rate_snapshot is not None else tarifa_usuario.get(imp.user_id)
    return float(imp.hours or 0) * float(tarifa or 0)


def _load_fact_imputations(db, conn, since: Optional[date]) -> int:
    from app.models.imputation import Imputation
    from app.models.project import Project
    from app.models.user import User
    q = db.query(Imputation)
    if since is not None:
        q = q.filter(Imputation.date >= since)
    rows = q.all()
    _ensure_dim_date(conn, [r.date for r in rows])
    tarifa = {i: r for i, r in db.query(User.id, User.hourly_rate)}
    empresa = {i: o for i, o in db.query(Project.id, Project.organization_id)}
    filas = [[imp.id, _date_key(imp.date), imp.project_id, imp.user_id,
              imp.organization_id or empresa.get(imp.project_id),
              float(imp.hours or 0), float(imp.hours or 0) if imp.is_billable else 0.0,
              _coste_de(imp, tarifa), bool(imp.is_billable), imp.task_id] for imp in rows]
    if since is None:
        return _vaciar_y_cargar(conn, "fact_imputations", 10, filas)
    conn.execute("DELETE FROM fact_imputations WHERE date_key >= ?", [_date_key(since)])
    if filas:
        conn.executemany("INSERT INTO fact_imputations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", filas)
    return len(filas)


def _load_fact_projects(db, conn) -> int:
    from sqlalchemy import case, func
    from app.models.financial import ProjectMilestone
    from app.models.imputation import Imputation
    from app.models.project import Project
    from app.models.task import Task, TaskStatus
    from app.models.user import User

    tarifa = {i: r for i, r in db.query(User.id, User.hourly_rate)}
    horas, coste = {}, {}
    for imp in db.query(Imputation).all():
        horas[imp.project_id] = horas.get(imp.project_id, 0.0) + float(imp.hours or 0)
        coste[imp.project_id] = coste.get(imp.project_id, 0.0) + _coste_de(imp, tarifa)
    tareas = {p: (n, h) for p, n, h in db.query(
        Task.project_id, func.count(Task.id), func.sum(case((Task.status == TaskStatus.done, 1), else_=0))
    ).group_by(Task.project_id)}
    hitos = {p: (n, h) for p, n, h in db.query(
        ProjectMilestone.project_id, func.count(ProjectMilestone.id),
        func.sum(case((ProjectMilestone.is_completed.is_(True), 1), else_=0))
    ).group_by(ProjectMilestone.project_id)}

    filas = []
    for p in db.query(Project).all():
        presupuesto = float(p.budget_amount or 0)
        # Ingresos: el importe del contrato; sin él, el presupuesto (como antes).
        ingresos = float(p.contract_amount or 0) or presupuesto
        total = coste.get(p.id, 0.0)
        margen = ingresos - total
        n_t, h_t = tareas.get(p.id, (0, 0))
        n_m, h_m = hitos.get(p.id, (0, 0))
        filas.append([p.id, p.organization_id, _date_key(p.start_date),
                      _date_key(p.end_date_real or p.end_date_planned), presupuesto, horas.get(p.id, 0.0), total,
                      ingresos, margen, round(margen / ingresos * 100, 1) if ingresos else 0.0,
                      int(n_t or 0), int(h_t or 0), int(n_m or 0), int(h_m or 0), _valor(p.risk_level), _valor(p.status)])
    _ensure_dim_date(conn, [d for p in db.query(Project.start_date, Project.end_date_real, Project.end_date_planned)
                            for d in p if d])
    return _vaciar_y_cargar(conn, "fact_projects", 16, filas)


def _load_fact_pipeline(db, conn) -> int:
    from app.models.pipeline import Opportunity
    rows = db.query(Opportunity).all()
    _ensure_dim_date(conn, [d for o in rows for d in (o.expected_close_date, _dia(o.created_at)) if d])
    filas = []
    for o in rows:
        creada = _dia(o.created_at)
        etapa = _valor(o.stage)
        esperado, prob = float(o.expected_revenue or 0), float(o.probability or 0)
        filas.append([o.id, o.organization_id, etapa, esperado, prob, esperado * prob / 100,
                      _date_key(o.expected_close_date), _date_key(creada), o.client_id, o.owner_id,
                      _valor(o.contract_type), etapa == "won", etapa == "lost",
                      (timeutil.today() - creada).days if creada else None])
    return _vaciar_y_cargar(conn, "fact_pipeline", 14, filas)


def _load_fact_tickets(db, conn) -> int:
    from app.models.service_desk import Ticket
    rows = db.query(Ticket).all()
    _ensure_dim_date(conn, [d for t in rows for d in (_dia(t.created_at), _dia(t.closed_at or t.resolved_at)) if d])
    filas = []
    for t in rows:
        cierre = t.closed_at or t.resolved_at
        horas = None
        if t.created_at and cierre:
            a, b = t.created_at, cierre
            if (a.tzinfo is None) != (b.tzinfo is None):
                a, b = a.replace(tzinfo=None), b.replace(tzinfo=None)
            horas = round((b - a).total_seconds() / 3600, 2)
        filas.append([t.id, t.organization_id, _date_key(_dia(t.created_at)), _date_key(_dia(cierre)),
                      _valor(t.status), _valor(t.priority), _valor(t.ticket_type),
                      t.service_item_id,   # «categoría»: el elemento del catálogo de servicios
                      t.assigned_to_user_id, t.client_id, horas,
                      bool(t.sla_resolution_breached or t.sla_response_breached), t.csat_score])
    return _vaciar_y_cargar(conn, "fact_tickets", 13, filas)


def _apuntar(conn, estado: str, detalle: dict) -> None:
    import json
    from datetime import timezone
    # En UTC y sin zona: `now()` de DuckDB guardaba la hora local en una columna sin zona.
    ahora = datetime.now(timezone.utc).replace(tzinfo=None)
    conn.execute("INSERT INTO etl_runs VALUES (?, ?, ?)", [ahora, estado, json.dumps(detalle, default=str)])


def estado(org: Optional[str]) -> dict:
    """La última carga (y la última buena) y cuántas filas de la empresa hay en cada hecho."""
    import json
    conn = get_duckdb_conn()
    try:
        def fila(sql):
            r = conn.execute(sql).fetchone()
            return {"run_at": str(r[0]), "status": r[1], "detail": json.loads(r[2] or "{}")} if r else None
        ultima = fila("SELECT run_at, status, detail FROM etl_runs ORDER BY run_at DESC LIMIT 1")
        buena = fila("SELECT run_at, status, detail FROM etl_runs WHERE status = 'ok' ORDER BY run_at DESC LIMIT 1")
        filas = {t: conn.execute(f"SELECT count(*) FROM {t} WHERE organization_id = ?", [org]).fetchone()[0]  # noqa: S608
                 for t in ("fact_imputations", "fact_projects", "fact_pipeline", "fact_tickets")}
    finally:
        conn.close()
    return {"last_run": ultima, "last_ok": buena, "company_rows": filas}


# ── Public API ────────────────────────────────────────────────────────────────

def run_full_etl(db, since: Optional[date] = None) -> dict:
    """Carga PostgreSQL → DuckDB.

    Sin `since` (lo normal, y lo que hace el trabajo nocturno) es una recarga
    completa: el almacén queda igual que Postgres, incluido lo borrado. Con
    `since`, sólo las imputaciones desde esa fecha (las dimensiones y el resto de
    hechos se recargan enteros igualmente). Todo en una transacción de DuckDB:
    si algo falla, se queda lo que había.
    """
    import time
    inicio = time.monotonic()
    conn = get_duckdb_conn()
    try:
        logger.info("OLAP ETL start (since=%s)", since)
        conn.execute("BEGIN TRANSACTION")
        result = {
            "status": "ok",
            "since": str(since) if since else "full",
            "organizations": _load_dim_organizations(db, conn),
            "clients": _load_dim_clients(db, conn),
            "users": _load_dim_users(db, conn),
            "dim_projects": _load_dim_projects(db, conn),
            "imputations": _load_fact_imputations(db, conn, since),
            "projects": _load_fact_projects(db, conn),
            "pipeline": _load_fact_pipeline(db, conn),
            "tickets": _load_fact_tickets(db, conn),
        }
        result["seconds"] = round(time.monotonic() - inicio, 2)
        _apuntar(conn, "ok", result)
        conn.execute("COMMIT")
        logger.info("OLAP ETL complete: %s", result)
        return result
    except Exception as exc:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            logger.debug("OLAP ETL: rollback sin transacción abierta", exc_info=True)
        try:
            _apuntar(conn, "error", {"error": f"{type(exc).__name__}: {exc}"[:500]})
        except Exception:
            logger.debug("OLAP ETL: no se pudo apuntar el fallo", exc_info=True)
        logger.error("OLAP ETL failed: %s", exc, exc_info=True)
        raise
    finally:
        conn.close()
