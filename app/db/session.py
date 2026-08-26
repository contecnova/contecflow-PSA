"""
session.py — Configuración de base de datos con soporte dual SQLite / PostgreSQL.

- SQLite:     DATABASE_URL no definida, o empieza por sqlite:///  → desarrollo local
- PostgreSQL: DATABASE_URL=postgresql://user:pass@host:5432/dbname → producción

Para migrar datos de SQLite a PostgreSQL:
  python -m app.db.migrate_to_pg
"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


def _extract_model_class(entity):
    """Return the ORM mapped class from an entity (class, InstrumentedAttribute, etc.)."""
    if isinstance(entity, type):
        return entity
    # InstrumentedAttribute e.g. Project.id, Project.name
    if hasattr(entity, "class_"):
        return entity.class_
    # Label / AnnotatedColumn
    if hasattr(entity, "property") and hasattr(entity.property, "parent"):
        try:
            return entity.property.parent.class_
        except Exception:
            logger.debug("_extract_model_class: fallo best-effort ignorado", exc_info=True)
    return None


class TenantIsolationError(RuntimeError):
    """No se puede demostrar el aislamiento de tenant para una consulta.

    Se lanza en vez de devolver la consulta sin filtrar. Un 500 es un incidente
    que se investiga; una consulta sin filtro de tenant es una fuga silenciosa
    entre clientes que nadie ve (auditoría 2026-08, P1-7).
    """


def _is_tenant_exempt(model) -> bool:
    """¿Está el modelo exento del filtro automático, de forma declarada?

    La exención se declara en el propio modelo con ``_tenant_exempt = True`` (ver
    app/models/mfa.py::Organization), no aquí, para que se vea al leerlo. Un
    modelo al que simplemente le falte la columna de tenant NO está exento: eso
    era el fail-open que este cambio elimina.
    """
    return getattr(model, "_tenant_exempt", False) is True


def _tenant_filter_for_model(query, model, org_id):
    """Inject tenant isolation filter into *query* for the given *model*.

    Precedence:
    1. Model has ``organization_id`` column directly → filter by it.
    2. Model has ``org_id`` column → filter by it.
    3. Model has a ``project_id`` FK column → use a subquery against projects.
    4. Model has a direct FK to users → use a subquery against users.
    5. Model has ``actor_id`` → use a subquery against users.
    6. Model declares ``_tenant_exempt = True`` → pasa sin filtrar, con motivo.
    7. Nada de lo anterior → ``TenantIsolationError`` (fail-closed).

    El paso 7 antes era "devolver la consulta sin filtrar, más seguro que
    petar". No lo era: convertía cada modelo nuevo sin columna de tenant en una
    fuga entre clientes que ninguna prueba detectaba.
    """
    if org_id is None:
        return query

    if hasattr(model, "organization_id"):
        # Some models (e.g. AppSetting) mark themselves to also include
        # global (org_id IS NULL) rows alongside tenant-specific ones.
        if getattr(model, "_tenant_filter_include_global", False):
            from sqlalchemy import or_
            return query.filter(
                or_(model.organization_id == org_id, model.organization_id.is_(None))
            )
        return query.filter(model.organization_id == org_id)

    if hasattr(model, "org_id"):
        return query.filter(model.org_id == org_id)

    # Subquery route — avoids JOIN conflicts on already-joined queries.
    if hasattr(model, "project_id"):
        from sqlalchemy import select as sa_select
        from app.models.project import Project
        project_ids_sq = (
            sa_select(Project.id)
            .where(Project.organization_id == org_id)
            .scalar_subquery()
        )
        return query.filter(model.project_id.in_(project_ids_sq))

    if hasattr(model, "user_id"):
        from sqlalchemy import select as sa_select
        from app.models.user import User
        user_ids_sq = (
            sa_select(User.id)
            .where(User.organization_id == org_id)
            .scalar_subquery()
        )
        return query.filter(model.user_id.in_(user_ids_sq))

    # Fallback: models (e.g. ActivityEvent) that link to users via actor_id
    if hasattr(model, "actor_id"):
        from sqlalchemy import select as sa_select
        from app.models.user import User
        user_ids_sq = (
            sa_select(User.id)
            .where(User.organization_id == org_id)
            .scalar_subquery()
        )
        return query.filter(model.actor_id.in_(user_ids_sq))

    if _is_tenant_exempt(model):
        return query

    raise TenantIsolationError(
        f"{getattr(model, '__name__', model)} no tiene columna de tenant "
        "(organization_id / org_id / project_id / user_id / actor_id) ni declara "
        "_tenant_exempt = True. No se puede aislar por organización: revisa el "
        "modelo antes de consultarlo desde una petición de usuario."
    )


def _extract_models_from_select(stmt):
    """Return ORM model classes referenced by a SA 2.0 Select statement.

    Resolves Table objects from stmt.froms back to their mapped class via
    SA 2.0's public registry API (Base.registry.mappers).
    """
    from sqlalchemy import Table

    models: list = []
    seen: set = set()
    try:
        froms = list(stmt.froms)
    except Exception:
        return models

    if not froms:
        return models

    try:
        from app.db.base import Base
        table_to_class = {
            mapper.persist_selectable: mapper.class_
            for mapper in Base.registry.mappers
        }
    except Exception:
        return models

    for from_clause in froms:
        if isinstance(from_clause, Table):
            cls = table_to_class.get(from_clause)
            if cls is not None and cls not in seen:
                seen.add(cls)
                models.append(cls)

    return models


def _tenant_where_for_model(stmt, model, org_id):
    """Inject tenant isolation into a SA 2.0 Select statement via .where().

    Mirrors _tenant_filter_for_model but operates on Select objects instead
    of legacy Query objects — incluida la misma política fail-closed.
    """
    if org_id is None:
        return stmt

    if hasattr(model, "organization_id"):
        if getattr(model, "_tenant_filter_include_global", False):
            from sqlalchemy import or_
            return stmt.where(or_(model.organization_id == org_id, model.organization_id.is_(None)))
        return stmt.where(model.organization_id == org_id)

    if hasattr(model, "org_id"):
        return stmt.where(model.org_id == org_id)

    if hasattr(model, "project_id"):
        from sqlalchemy import select as sa_select
        from app.models.project import Project
        project_ids_sq = (
            sa_select(Project.id)
            .where(Project.organization_id == org_id)
            .scalar_subquery()
        )
        return stmt.where(model.project_id.in_(project_ids_sq))

    if hasattr(model, "user_id"):
        from sqlalchemy import select as sa_select
        from app.models.user import User
        user_ids_sq = (
            sa_select(User.id)
            .where(User.organization_id == org_id)
            .scalar_subquery()
        )
        return stmt.where(model.user_id.in_(user_ids_sq))

    if hasattr(model, "actor_id"):
        from sqlalchemy import select as sa_select
        from app.models.user import User
        user_ids_sq = (
            sa_select(User.id)
            .where(User.organization_id == org_id)
            .scalar_subquery()
        )
        return stmt.where(model.actor_id.in_(user_ids_sq))

    if _is_tenant_exempt(model):
        return stmt

    raise TenantIsolationError(
        f"{getattr(model, '__name__', model)} no tiene columna de tenant ni declara "
        "_tenant_exempt = True. No se puede aislar por organización."
    )


class TenantSession(Session):
    """SQLAlchemy session that transparently injects tenant (org) isolation.

    When ``db.info["organization_id"]`` is set the session automatically adds
    WHERE clauses so that every ORM query is scoped to the current tenant.
    Superadmin requests set the value to *None*, which disables filtering and
    allows full cross-tenant visibility.
    """

    def query(self, *entities, **kwargs):
        q = super().query(*entities, **kwargs)

        # is_superadmin is explicitly set by deps.get_current_user:
        #   True  → superadmin, bypass all tenant filters
        #   False → regular user, enforce tenant isolation
        #   None  → session not initialised by a request (background job / test)
        #           → bypass for backward compatibility
        is_superadmin = self.info.get("is_superadmin", None)
        if is_superadmin is None or is_superadmin is True:
            return q

        org_id = self.info.get("organization_id")
        if org_id is None:
            # Regular user with no organisation assigned — block cross-tenant leakage
            # by returning an empty result set instead of bypassing all filters.
            from sqlalchemy import false as sql_false
            return q.filter(sql_false())

        # Resolve all entities to mapped model classes (handles both class
        # and InstrumentedAttribute patterns, e.g. db.query(Project.id)).
        # Deduplicate so a model appearing multiple times (e.g. self-join) only
        # gets one filter clause, preserving query correctness and performance.
        seen: set = set()
        models: list = []
        for e in entities:
            candidate = _extract_model_class(e)
            if candidate is not None and candidate not in seen:
                seen.add(candidate)
                models.append(candidate)

        if not models:
            return q

        # Apply tenant isolation for every resolved model so that all tables
        # in a multi-entity JOIN are scoped to the current tenant, not just
        # the first one.
        # Fail-closed (auditoría 2026-08, P1-7). Antes esto era
        # `except Exception: logger.debug(...)`, así que si el filtro fallaba para
        # un modelo la consulta seguía SIN filtro de tenant y solo quedaba rastro
        # en un log de nivel debug. Un error propagado es un incidente que se
        # investiga; una consulta sin filtrar es una fuga que nadie ve.
        for model in models:
            q = _tenant_filter_for_model(q, model, org_id)

        return q

    def execute(self, statement, *args, **kwargs):
        """SA 2.0 execute() override — applies tenant isolation to ORM Select statements.

        db.query() intercepts the legacy SA 1.x API; this method covers the
        modern SA 2.0 pattern: db.execute(select(Model).where(...)).
        Non-Select statements (INSERT, UPDATE, DELETE, raw SQL) pass through
        unchanged — they carry explicit WHERE clauses by design.
        """
        from sqlalchemy.sql import Select
        if isinstance(statement, Select):
            is_superadmin = self.info.get("is_superadmin", None)
            if is_superadmin is False:
                org_id = self.info.get("organization_id")
                if org_id is None:
                    from sqlalchemy import false as sql_false
                    statement = statement.where(sql_false())
                else:
                    # Fail-closed, igual que en query(). Ver el comentario de allí.
                    for model in _extract_models_from_select(statement):
                        statement = _tenant_where_for_model(statement, model, org_id)
        return super().execute(statement, *args, **kwargs)

_url = settings.DATABASE_URL
_is_sqlite = _url.startswith("sqlite")

# ── Opciones según motor ───────────────────────────────────────────────────────
if _is_sqlite:
    engine = create_engine(
        _url,
        connect_args={"check_same_thread": False},
        echo=False,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA cache_size=-64000")
        cur.execute("PRAGMA temp_store=MEMORY")
        cur.execute("PRAGMA mmap_size=268435456")
        cur.execute("PRAGMA busy_timeout=10000")
        cur.close()

else:
    # PostgreSQL — pool optimizado para producción
    engine = create_engine(
        _url,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,       # reconecta automáticamente si la conexión muere
        pool_recycle=3600,        # recicla conexiones cada hora
        echo=False,
    )


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=TenantSession)


# ── Audit #C5: global tenant isolation via do_orm_execute ─────────────────────
#
# `TenantSession.query()` and `.execute(Select)` already inject org filters for
# the common code paths. The remaining gap is lazy-loaded relationships and any
# raw `session.execute(select(Model))` that bypasses our overrides at runtime
# (e.g. SA internals during refresh).
#
# `do_orm_execute` is SA 2.0's canonical hook for this: it fires for every ORM
# statement and lets us attach `with_loader_criteria` clauses that the SA
# planner applies wherever the model appears (including eager/lazy joins).
#
# Bypass options:
#   • `session.info["is_superadmin"] = True` — already used for superadmin paths.
#   • `session.info["bypass_tenant_filter"] = True` — explicit per-session escape
#     hatch for migration scripts / cross-tenant analytics jobs.
#   • Set env `TENANT_AUTO_FILTER_GLOBAL=0` to disable the event entirely.

import os as _os
from sqlalchemy import event as _sa_event
from sqlalchemy.orm import with_loader_criteria as _with_loader_criteria

_TENANT_AUTO_FILTER_GLOBAL = _os.getenv("TENANT_AUTO_FILTER_GLOBAL", "1") == "1"


def _iter_tenant_scoped_models():
    """Yield mapped ORM classes that carry an `organization_id` column."""
    try:
        from app.db.base import Base
    except Exception:
        return
    for mapper in Base.registry.mappers:
        cls = mapper.class_
        if hasattr(cls, "organization_id"):
            yield cls


if _TENANT_AUTO_FILTER_GLOBAL:

    @_sa_event.listens_for(SessionLocal, "do_orm_execute")
    def _enforce_tenant_isolation(execute_state) -> None:
        # Only filter ORM SELECT statements; INSERT/UPDATE/DELETE carry their
        # own WHERE clauses and would be incorrectly narrowed otherwise.
        if not execute_state.is_select:
            return
        if execute_state.is_relationship_load:
            # Relationship loads already inherit their parent's tenant scope
            # (parent row was filtered when loaded). Skipping avoids double
            # filtering joined-eager loads where the cross-table FK is the
            # legitimate access path.
            return

        session = execute_state.session
        info = getattr(session, "info", {}) or {}

        if info.get("bypass_tenant_filter") is True:
            return
        is_superadmin = info.get("is_superadmin", None)
        if is_superadmin is None or is_superadmin is True:
            # Uninitialised session (background job, test) or superadmin: skip.
            return
        org_id = info.get("organization_id")
        if org_id is None:
            # Regular user with no org → block any data return.
            from sqlalchemy import false as _sql_false
            execute_state.statement = execute_state.statement.options(
                _with_loader_criteria(
                    object,  # base — will be skipped by SA when no class matches
                    lambda cls: _sql_false(),
                    include_aliases=True,
                )
            )
            return

        # Attach a loader_criteria for every tenant-scoped model. SA filters out
        # criteria whose target class is not in the statement, so the cost is
        # mostly evaluation at plan time, not execution.
        criteria_options = []
        for model in _iter_tenant_scoped_models():
            include_global = getattr(model, "_tenant_filter_include_global", False)
            if include_global:
                from sqlalchemy import or_ as _or
                criteria_options.append(
                    _with_loader_criteria(
                        model,
                        lambda cls, _org=org_id: _or(
                            cls.organization_id == _org,
                            cls.organization_id.is_(None),
                        ),
                        include_aliases=True,
                    )
                )
            else:
                criteria_options.append(
                    _with_loader_criteria(
                        model,
                        lambda cls, _org=org_id: cls.organization_id == _org,
                        include_aliases=True,
                    )
                )
        if criteria_options:
            execute_state.statement = execute_state.statement.options(*criteria_options)


def get_db() -> Generator[Session, None, None]:
    """
    Yield a synchronous SQLAlchemy session for request-scoped DB access.

    Contecflow uses synchronous SQLAlchemy ORM as its default persistence layer.
    Any endpoint that needs database access must be declared as a regular
    synchronous function (`def`) so that database work runs safely in FastAPI's
    threadpool. Async endpoints are allowed only for non-blocking I/O / event
    streaming; they must not call `get_db()` directly.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


from contextlib import contextmanager  # noqa: E402


@contextmanager
def worker_db_session() -> Generator[Session, None, None]:
    """Context manager para Celery workers / scripts CLI.

    Garantiza el `db.close()` incluso si la task lanza una excepción no
    capturada (a diferencia de `db = SessionLocal()` + try/finally manual).
    Resuelve audit #29 ("SessionLocal sin context manager en worker.py").

    Uso::

        with worker_db_session() as db:
            do_work(db)
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def is_postgres() -> bool:
    return not _is_sqlite


def get_db_type() -> str:
    return "postgresql" if not _is_sqlite else "sqlite"
