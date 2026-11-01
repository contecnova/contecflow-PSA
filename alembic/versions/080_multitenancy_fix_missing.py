"""multitenancy_fix_missing — add organization_id to tables that 076 missed.

La migración 076 (multitenancy_org_id_columns) usó una lista hardcoded de
nombres de tabla. El script generador adivinó muchos nombres incorrectamente
(ej. `service_items` cuando la tabla real es `sd_service_items`, `tickets`
en lugar de `sd_tickets`). Resultado: ~218 tablas con `organization_id` en
el modelo SQLAlchemy pero SIN la columna en la BD, causando errores
500 en runtime (ej. POST /auth/login al consultar UserSession).

Esta migración resuelve eso vía introspección automática:
1. Importa todos los modelos de Base.metadata
2. Para cada tabla con `organization_id` en su definición declarativa
3. Si la tabla existe en DB pero la columna falta, la añade + index + FK
4. Backfill con default org (creada en 076)

Idempotente: salta tablas inexistentes o columnas ya presentes.

Revision ID: 080_multitenancy_fix_missing
Revises: 079_more_soft_delete
Create Date: 2026-05-15
"""
from alembic import op
import sqlalchemy as sa


revision = "080_multitenancy_fix_missing"
down_revision = "079_more_soft_delete"
branch_labels = None
depends_on = None


DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000001"


def _model_tables_with_org_id() -> list[str]:
    """Devuelve los __tablename__ de todos los modelos cuya clase declara
    una columna `organization_id` (audit #7).
    """
    # Importar dentro para que la migración funcione sin app/main cargada.
    from app.db.base import Base
    import app.models  # noqa: F401 — carga todos los modelos

    out: list[str] = []
    for table in Base.metadata.sorted_tables:
        if "organization_id" in table.columns:
            out.append(table.name)
    return sorted(set(out))


def _table_exists(conn, table_name: str) -> bool:
    insp = sa.inspect(conn)
    return table_name in insp.get_table_names()


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    insp = sa.inspect(conn)
    try:
        cols = [c["name"] for c in insp.get_columns(table_name)]
    except Exception:
        return False
    return column_name in cols


def upgrade() -> None:
    conn = op.get_bind()
    is_sqlite = conn.dialect.name == "sqlite"

    # Asegurar default org (idempotente)
    try:
        result = conn.execute(
            sa.text("SELECT id FROM organizations WHERE id = :id"),
            {"id": DEFAULT_ORG_ID},
        ).first()
        if not result:
            conn.execute(
                sa.text(
                    "INSERT INTO organizations (id, name, slug, plan, is_active) "
                    "VALUES (:id, :name, :slug, :plan, true)"
                ),
                {
                    "id": DEFAULT_ORG_ID,
                    "name": "Default Organization",
                    "slug": "default",
                    "plan": "starter",
                },
            )
    except Exception:
        pass

    tables = _model_tables_with_org_id()
    for table in tables:
        if not _table_exists(conn, table):
            continue
        if _column_exists(conn, table, "organization_id"):
            continue
        # `organizations` no debe tener self-referencia
        if table == "organizations":
            continue
        # Tablas con `org_id` legacy: saltar, la coexistencia es intencional
        if _column_exists(conn, table, "org_id"):
            continue

        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("organization_id", sa.String(36), nullable=True))
            try:
                batch.create_index(f"ix_{table}_organization_id", ["organization_id"])
            except Exception:
                pass
            if not is_sqlite:
                try:
                    batch.create_foreign_key(
                        f"fk_{table}_organization_id",
                        "organizations",
                        ["organization_id"],
                        ["id"],
                    )
                except Exception:
                    pass

        # Backfill con default org
        conn.execute(
            sa.text(
                f"UPDATE {table} SET organization_id = :org "
                "WHERE organization_id IS NULL"
            ),
            {"org": DEFAULT_ORG_ID},
        )


def downgrade() -> None:
    conn = op.get_bind()
    is_sqlite = conn.dialect.name == "sqlite"
    tables = _model_tables_with_org_id()
    for table in tables:
        if not _table_exists(conn, table):
            continue
        if not _column_exists(conn, table, "organization_id"):
            continue
        if table == "organizations":
            continue
        with op.batch_alter_table(table) as batch:
            try:
                batch.drop_index(f"ix_{table}_organization_id")
            except Exception:
                pass
            if not is_sqlite:
                try:
                    batch.drop_constraint(
                        f"fk_{table}_organization_id", type_="foreignkey"
                    )
                except Exception:
                    pass
            batch.drop_column("organization_id")
