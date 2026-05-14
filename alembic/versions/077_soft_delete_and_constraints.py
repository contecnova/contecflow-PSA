"""soft-delete + User.organization_id NOT NULL + unique per-tenant

Audit #36 — añade `is_active` (Boolean, default True, NOT NULL) a 8 modelos
multi-tenant que carecían de soft-delete: tasks, task_comments, alerts,
sd_configuration_items, project_phases, review_cycles, review_360_campaigns,
development_plans.

Audit #37 — `users.organization_id` pasa de nullable=True a NOT NULL.
Backfill previo: cualquier user con NULL → default org (creada en 076).

Audit #38 — unique constraints globales que deberían ser per-tenant:
  - tasks.code              → uq_task_code_per_org (organization_id, code)
  - sd_configuration_items.code → uq_sd_ci_code_per_org
  - sd_assets.code          → uq_sd_asset_code_per_org
  - alm_cost_centers.code   → uq_alm_cost_center_code_per_org

La migración usa `op.batch_alter_table` para compatibilidad con SQLite
(que no soporta ALTER COLUMN ni DROP CONSTRAINT directos).

Revision ID: 077_soft_delete_constraints
Revises: 076_multitenancy_org_id
Create Date: 2026-05-14
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "077_soft_delete_constraints"
down_revision = "076_multitenancy_org_id"
branch_labels = None
depends_on = None


# Default organization creada en migración 076.
DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000001"


# Audit #36 — modelos que reciben is_active.
SOFT_DELETE_TABLES = [
    "tasks",
    "task_comments",
    "alerts",
    "sd_configuration_items",
    "project_phases",
    "review_cycles",
    "review_360_campaigns",
    "development_plans",
]


# Audit #38 — (tabla, columna_unique_a_partir_de_la_que_se_genera, nombre_nuevo_constraint).
PER_TENANT_UNIQUES = [
    ("tasks",                 "code", "uq_task_code_per_org"),
    ("sd_configuration_items", "code", "uq_sd_ci_code_per_org"),
    ("sd_assets",             "code", "uq_sd_asset_code_per_org"),
    ("alm_cost_centers",      "code", "uq_alm_cost_center_code_per_org"),
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


def _find_unique_constraint(conn, table_name, column_name):
    """Devuelve el nombre del unique constraint sobre `column_name` en `table_name`.

    Busca también UNIQUE INDEXes (SQLite suele exponerlos como índices).
    """
    insp = sa.inspect(conn)
    try:
        for uc in insp.get_unique_constraints(table_name):
            cols = uc.get("column_names") or []
            if cols == [column_name]:
                return uc.get("name")
    except Exception:
        pass
    try:
        for ix in insp.get_indexes(table_name):
            if ix.get("unique") and ix.get("column_names") == [column_name]:
                return ix.get("name")
    except Exception:
        pass
    return None


def upgrade() -> None:
    conn = op.get_bind()

    # ── Audit #36: soft-delete is_active ────────────────────────────────────
    for table in SOFT_DELETE_TABLES:
        if not _table_exists(conn, table):
            continue
        if _column_exists(conn, table, "is_active"):
            # Ya existe (probablemente de una migración previa), nos saltamos.
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
        # Backfill explícito (server_default ya cubre las filas nuevas, pero
        # nos aseguramos de que no haya nulls residuales de algún motor).
        conn.execute(sa.text(f"UPDATE {table} SET is_active = 1 WHERE is_active IS NULL"))
        # Index para búsquedas de "solo activos".
        try:
            op.create_index(
                f"ix_{table}_is_active",
                table,
                ["is_active"],
            )
        except Exception:
            # Si ya existe (idempotencia), continuamos.
            pass

    # ── Audit #37: users.organization_id NOT NULL ───────────────────────────
    if _table_exists(conn, "users") and _column_exists(conn, "users", "organization_id"):
        # 1) Backfill — cualquier user huérfano apunta a la default org.
        conn.execute(
            sa.text(
                "UPDATE users SET organization_id = :org_id "
                "WHERE organization_id IS NULL"
            ),
            {"org_id": DEFAULT_ORG_ID},
        )
        # 2) ALTER COLUMN nullable=False (con batch para SQLite compat).
        with op.batch_alter_table("users") as batch:
            batch.alter_column(
                "organization_id",
                existing_type=sa.String(length=36),
                nullable=False,
            )

    # ── Audit #38: unique constraints per-tenant ───────────────────────────
    # Strategy: en SQLite los UNIQUE en columnas individuales se exponen como
    # índices (no como constraints nombrados). Necesitamos dropear el índice
    # ANTES del batch_alter_table porque batch.drop_constraint() falla al
    # encontrar un constraint inexistente al flush.
    insp = sa.inspect(conn)
    for table, column, new_name in PER_TENANT_UNIQUES:
        if not _table_exists(conn, table):
            continue
        if not _column_exists(conn, table, column):
            continue

        # 1) Intentar dropear índice unique existente sobre la columna sola.
        try:
            for ix in insp.get_indexes(table):
                if ix.get("unique") and ix.get("column_names") == [column]:
                    op.drop_index(ix.get("name"), table_name=table)
                    break
        except Exception:
            pass

        # 2) Intentar dropear constraint unique (Postgres) sobre la columna sola.
        existing_named = None
        try:
            for uc in insp.get_unique_constraints(table):
                cols = uc.get("column_names") or []
                if cols == [column]:
                    existing_named = uc.get("name")
                    break
        except Exception:
            pass

        # 3) Crear el nuevo constraint compuesto (organization_id, columna).
        with op.batch_alter_table(table) as batch:
            if existing_named:
                try:
                    batch.drop_constraint(existing_named, type_="unique")
                except Exception:
                    pass
            try:
                batch.create_unique_constraint(
                    new_name,
                    ["organization_id", column],
                )
            except Exception:
                # Si ya existe (idempotencia), continuamos.
                pass


def downgrade() -> None:
    conn = op.get_bind()

    # ── Revertir #38 ─────────────────────────────────────────────────────────
    for table, column, new_name in PER_TENANT_UNIQUES:
        if not _table_exists(conn, table):
            continue
        with op.batch_alter_table(table) as batch:
            try:
                batch.drop_constraint(new_name, type_="unique")
            except Exception:
                pass
            try:
                batch.create_unique_constraint(f"uq_{table}_{column}", [column])
            except Exception:
                pass

    # ── Revertir #37 ─────────────────────────────────────────────────────────
    if _table_exists(conn, "users") and _column_exists(conn, "users", "organization_id"):
        with op.batch_alter_table("users") as batch:
            batch.alter_column(
                "organization_id",
                existing_type=sa.String(length=36),
                nullable=True,
            )

    # ── Revertir #36 ─────────────────────────────────────────────────────────
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
