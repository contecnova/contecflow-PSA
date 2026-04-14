"""
session.py — Configuración de base de datos con soporte dual SQLite / PostgreSQL.

- SQLite:     DATABASE_URL no definida, o empieza por sqlite:///  → desarrollo local
- PostgreSQL: DATABASE_URL=postgresql://user:pass@host:5432/dbname → producción

Para migrar datos de SQLite a PostgreSQL:
  python -m app.db.migrate_to_pg
"""
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator
from app.core.config import settings


def _tenant_filter_for_model(query, model, org_id):
    if org_id is None:
        return query

    if hasattr(model, "organization_id"):
        return query.filter(model.organization_id == org_id)

    if hasattr(model, "org_id"):
        return query.filter(model.org_id == org_id)

    try:
        mapper = inspect(model)
    except Exception:
        return query

    from app.models.project import Project
    from app.models.user import User

    for rel in mapper.relationships:
        target = rel.mapper.class_
        if target is User:
            query = query.join(getattr(model, rel.key)).filter(User.organization_id == org_id)
            return query
        if target is Project:
            query = query.join(getattr(model, rel.key)).filter(Project.organization_id == org_id)
            return query

    return query


class TenantSession(Session):
    def query(self, *entities, **kwargs):
        q = super().query(*entities, **kwargs)
        org_id = self.info.get("organization_id")
        if org_id is None or len(entities) != 1:
            return q

        entity = entities[0]
        if isinstance(entity, type):
            try:
                return _tenant_filter_for_model(q, entity, org_id)
            except Exception:
                return q

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
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def is_postgres() -> bool:
    return not _is_sqlite


def get_db_type() -> str:
    return "postgresql" if not _is_sqlite else "sqlite"
