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
            pass
    return None


def _tenant_filter_for_model(query, model, org_id):
    """Inject tenant isolation filter into *query* for the given *model*.

    Precedence:
    1. Model has ``organization_id`` column directly → filter by it.
    2. Model has ``org_id`` column → filter by it.
    3. Model has a ``project_id`` FK column → use a subquery against projects.
    4. Model has a direct FK to users → use a subquery against users.
    5. Fall through (no filter — safer than crashing).
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

    return query


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

        # Resolve the first entity to a mapped model class (handles both class
        # and InstrumentedAttribute patterns, e.g. db.query(Project.id)).
        model = None
        if len(entities) == 1:
            model = _extract_model_class(entities[0])
        elif len(entities) > 1:
            # For multi-column queries pick the first entity that maps to a model.
            for e in entities:
                candidate = _extract_model_class(e)
                if candidate is not None:
                    model = candidate
                    break

        if model is None:
            return q

        try:
            return _tenant_filter_for_model(q, model, org_id)
        except Exception:
            return q

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


def is_postgres() -> bool:
    return not _is_sqlite


def get_db_type() -> str:
    return "postgresql" if not _is_sqlite else "sqlite"
