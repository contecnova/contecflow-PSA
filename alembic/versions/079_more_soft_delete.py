"""more soft-delete (#36 continuation) — 10 additional multi-tenant entities

Audit #36 (continuación) — añade `is_active` (Boolean, default True, NOT NULL,
index) a 10 modelos multi-tenant adicionales que carecían de soft-delete:

    ai_providers              — config de proveedor de IA
    expenses                  — gasto con workflow de aprobación
    issue_types               — tipo custom de issue por proyecto
    esign_envelopes           — sobre de firma electrónica
    user_cost_profiles        — perfil de coste versionado por usuario
    country_employer_costs    — defaults de coste-empresa por país
    raci_entries              — celda de matriz RACI
    sprint_retro_notes        — notas de retrospectiva por sprint
    project_changelog_entries — entrada de changelog del proyecto
    uat_cases                 — caso UAT (test de aceptación)
    sem_profiles              — perfil semántico de un agente

Estos modelos comparten el patrón "entity" (no son logs/audits/snapshots).
Los servicios que hoy hacen `db.delete(obj)` deberían pasar a usar
`obj.is_active = False` para preservar trazabilidad (cambio aplicado en un
commit subsiguiente fuera de la migración).

Idéntica estrategia a 077_soft_delete_constraints: `batch_alter_table` para
compatibilidad SQLite + backfill explícito + índice `ix_<table>_is_active`.

Revision ID: 079_more_soft_delete
Revises: 078_normalize_task_status_review
Create Date: 2026-05-15
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "079_more_soft_delete"
down_revision = "078_normalize_task_status_review"
branch_labels = None
depends_on = None


# Tablas que reciben is_active (audit #36 continuación).
SOFT_DELETE_TABLES = [
    "ai_providers",
    "expenses",
    "issue_types",
    "esign_envelopes",
    "user_cost_profiles",
    "country_employer_costs",
    "raci_entries",
    "sprint_retro_notes",
    "project_changelog_entries",
    "uat_cases",
    "sem_profiles",
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
            # Idempotencia: ya existe (probablemente de una corrida previa).
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
        # Backfill — server_default ya cubre filas nuevas; nos aseguramos
        # de que no haya nulls residuales por motor de BD.
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
