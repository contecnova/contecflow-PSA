"""soft-delete remaining 3 entities (#36 final)

Audit #36 (final) — añade `is_active` (Boolean, default True, NOT NULL, index)
a los 3 modelos multi-tenant que aún carecían de soft-delete tras las
migraciones 077 y 079:

    projects              — entidad principal de proyecto (PSA core)
    timesheets            — parte horaria semanal por usuario
    portal_conversations  — hilo de conversación cliente-equipo en el portal

Con esta migración los 22 modelos identificados en la auditoría #36 quedan
homogéneamente soft-deletable. Los CRUD/servicios se actualizarán en commits
posteriores; esta migración es column-only.

Idéntica estrategia a 077/079: `batch_alter_table` para compatibilidad SQLite,
backfill explícito a 1 e índice `ix_<table>_is_active`.

Revision ID: 081_soft_delete_remaining
Revises: 080_multitenancy_fix_missing
Create Date: 2026-05-15
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "081_soft_delete_remaining"
down_revision = "080_multitenancy_fix_missing"
branch_labels = None
depends_on = None


# Tablas que reciben is_active (audit #36 final).
SOFT_DELETE_TABLES = [
    "projects",
    "timesheets",
    "portal_conversations",
]


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

    for table in SOFT_DELETE_TABLES:
        if not _table_exists(conn, table):
            continue
        if _column_exists(conn, table, "is_active"):
            # Idempotencia: ya existe (corrida previa).
            continue
        with op.batch_alter_table(table) as batch:
            batch.add_column(
                sa.Column(
                    "is_active",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("1"),
                )
            )
        # Backfill — server_default cubre filas nuevas; nos aseguramos de que
        # no queden nulls residuales según el motor de BD.
        conn.execute(sa.text(f"UPDATE {table} SET is_active = 1 WHERE is_active IS NULL"))
        # Index para queries "solo activos".
        try:
            op.create_index(
                f"ix_{table}_is_active",
                table,
                ["is_active"],
            )
        except Exception:
            # Idempotencia.
            pass


def downgrade() -> None:
    conn = op.get_bind()

    for table in SOFT_DELETE_TABLES:
        if not _table_exists(conn, table):
            continue
        if not _column_exists(conn, table, "is_active"):
            continue
        try:
            op.drop_index(f"ix_{table}_is_active", table_name=table)
        except Exception:
            pass
        with op.batch_alter_table(table) as batch:
            batch.drop_column("is_active")
