"""multitenancy_fix_unregistered_models — add organization_id to tables whose
models were not imported in app/models/__init__.py when migration 080 ran.

Migration 080 enumerated tables via `Base.metadata.sorted_tables` to detect
the org_id mismatch. But three model modules (`cab`, `automations`,
`expenses`) were not imported in `app/models/__init__.py`, so their classes
never got registered with Base.metadata at startup. Result: ~16 tables
(cab_votes, change_request_windows, webhook_triggers, email_logs,
gdpr_requests, integration_configs, calendar_events, automation_rules,
expenses, etc.) had `organization_id` declared in the Python model but
the column was missing in the DB → 500 on any endpoint hitting them.

This migration re-runs the auto-detection now that __init__.py imports
those modules. Identical body to 080; idempotent.

Revision ID: 082_multitenancy_fix_unregistered_models
Revises: 081_soft_delete_remaining
Create Date: 2026-05-16
"""
from alembic import op
import sqlalchemy as sa


revision = "082_multitenancy_fix_unregistered_models"
down_revision = "081_soft_delete_remaining"
branch_labels = None
depends_on = None


DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000001"


def _model_tables_with_org_id() -> list[str]:
    from app.db.base import Base
    import app.models  # noqa: F401 — now includes cab, automations, expenses

    out: list[str] = []
    for table in Base.metadata.sorted_tables:
        if "organization_id" in table.columns:
            out.append(table.name)
    return sorted(set(out))


def _table_exists(conn, table_name: str) -> bool:
    return table_name in sa.inspect(conn).get_table_names()


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    try:
        cols = [c["name"] for c in sa.inspect(conn).get_columns(table_name)]
    except Exception:
        return False
    return column_name in cols


def upgrade() -> None:
    conn = op.get_bind()
    is_sqlite = conn.dialect.name == "sqlite"

    for table in _model_tables_with_org_id():
        if not _table_exists(conn, table):
            continue
        if _column_exists(conn, table, "organization_id"):
            continue
        if table == "organizations":
            continue
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

        conn.execute(
            sa.text(
                f"UPDATE {table} SET organization_id = :org "
                "WHERE organization_id IS NULL"
            ),
            {"org": DEFAULT_ORG_ID},
        )


def downgrade() -> None:
    # No-op: 080 + 082 share the same column. Downgrading 082 would also
    # roll back columns added in 080. Use 080's downgrade path instead.
    pass
