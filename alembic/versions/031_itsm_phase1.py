"""031 – Fase 1 ITSM: Problem RCA columns + CMDB discovery tables

Revision ID: 031_itsm_phase1
Revises: 030_webhook_trigger_slug_rotation
Create Date: 2026-04-01
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "031_itsm_phase1"
down_revision = "030_webhook_trigger_slug_rotation"
branch_labels = None
depends_on = None


# ─── helpers ──────────────────────────────────────────────────────────────────

def _column_exists(table: str, column: str) -> bool:
    """Return True when *column* already exists in *table* (defensive upgrade)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = [c["name"] for c in inspector.get_columns(table)]
    return column in cols


def _table_exists(table: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table in inspector.get_table_names()


# ─── upgrade ──────────────────────────────────────────────────────────────────

def upgrade() -> None:
    # 1. Add new columns to sd_problems (Problem RCA enrichment)
    for col_name, col_type, kwargs in [
        ("rca_type", sa.String(30), {"nullable": True}),
        ("rca_ai_suggestion", sa.Text(), {"nullable": True}),
        ("auto_detected", sa.Boolean(), {"nullable": False, "server_default": sa.text("false")}),
        ("affected_services_json", sa.Text(), {"nullable": True}),
    ]:
        if not _column_exists("sd_problems", col_name):
            op.add_column(
                "sd_problems",
                sa.Column(col_name, col_type, **kwargs),
            )

    # 2. Add discovery columns to cmdb_items
    for col_name, col_type, kwargs in [
        ("external_id", sa.String(255), {"nullable": True}),
        ("discovery_provider", sa.String(50), {"nullable": True}),
        ("last_discovered_at", sa.DateTime(timezone=True), {"nullable": True}),
        ("is_discovered", sa.Boolean(), {"nullable": False, "server_default": sa.text("false")}),
    ]:
        if not _column_exists("cmdb_items", col_name):
            op.add_column(
                "cmdb_items",
                sa.Column(col_name, col_type, **kwargs),
            )

    # Index for quick external_id lookups
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_indexes = {
        idx["name"]
        for idx in inspector.get_indexes("cmdb_items")
    }
    if "ix_cmdb_items_external_id" not in existing_indexes:
        op.create_index(
            "ix_cmdb_items_external_id",
            "cmdb_items",
            ["external_id"],
        )

    # 3. Create cmdb_discovery_providers table
    if not _table_exists("cmdb_discovery_providers"):
        op.create_table(
            "cmdb_discovery_providers",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("provider_type", sa.String(30), nullable=False, index=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("config_json", sa.Text(), nullable=True),
            sa.Column(
                "organization_id",
                sa.String(36),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=True,
                index=True,
            ),
            sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_run_status", sa.String(20), nullable=True),
            sa.Column(
                "created_by",
                sa.String(36),
                sa.ForeignKey("users.id"),
                nullable=True,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                onupdate=sa.text("now()"),
                nullable=True,
            ),
        )

    # 4. Create cmdb_discovery_jobs table
    if not _table_exists("cmdb_discovery_jobs"):
        op.create_table(
            "cmdb_discovery_jobs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "provider_id",
                sa.String(36),
                sa.ForeignKey("cmdb_discovery_providers.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'running'")),
            sa.Column(
                "started_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("cis_created", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("cis_updated", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("cis_deactivated", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("summary_json", sa.Text(), nullable=True),
            sa.Column(
                "triggered_by",
                sa.String(20),
                nullable=False,
                server_default=sa.text("'scheduler'"),
            ),
        )


# ─── downgrade ────────────────────────────────────────────────────────────────

def downgrade() -> None:
    # Drop tables
    if _table_exists("cmdb_discovery_jobs"):
        op.drop_table("cmdb_discovery_jobs")
    if _table_exists("cmdb_discovery_providers"):
        op.drop_table("cmdb_discovery_providers")

    # Remove cmdb_items discovery columns
    for col_name in ("external_id", "discovery_provider", "last_discovered_at", "is_discovered"):
        if _column_exists("cmdb_items", col_name):
            op.drop_column("cmdb_items", col_name)

    # Remove sd_problems columns
    for col_name in ("rca_type", "rca_ai_suggestion", "auto_detected", "affected_services_json"):
        if _column_exists("sd_problems", col_name):
            op.drop_column("sd_problems", col_name)
