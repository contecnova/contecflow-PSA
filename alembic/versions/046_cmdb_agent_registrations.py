"""046 – CMDB on-premise agent registration table

Creates `cmdb_agent_registrations` to support lightweight on-premise
Windows/Linux agents that report their system inventory via a secure
Bearer-token check-in API.

Each row represents a single registered agent (one per host).  The token
is stored as a SHA-256 hash only — the raw token is returned once at
registration time and never again.

Revision ID: 046_cmdb_agent_registrations
Revises: 045_rca_templates_seed
Create Date: 2026-04-28
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "046_cmdb_agent_registrations"
down_revision = "045_rca_templates_seed"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return table_name in insp.get_table_names()


def upgrade() -> None:
    if _table_exists("cmdb_agent_registrations"):
        return

    op.create_table(
        "cmdb_agent_registrations",
        sa.Column("id",           sa.String(36),  primary_key=True),
        sa.Column("name",         sa.String(255), nullable=False),
        sa.Column("description",  sa.Text,        nullable=True),
        # Token stored as SHA-256 hex digest only (raw token never persisted)
        sa.Column("token_hash",   sa.String(64),  nullable=False, unique=True),
        # First 8 chars of raw token for display/audit (non-sensitive prefix)
        sa.Column("token_prefix", sa.String(8),   nullable=False),
        # OS hint set at registration or auto-detected at first checkin
        sa.Column("os_type",      sa.String(10),  nullable=True),   # windows | linux
        sa.Column("is_active",    sa.Boolean,     nullable=False, server_default=sa.text("true")),
        # Last check-in metadata
        sa.Column("last_checkin_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_checkin_ip", sa.String(45), nullable=True),
        sa.Column("last_hostname",   sa.String(255), nullable=True),
        # Optional FK to the CMDB item this agent manages (set after first checkin)
        sa.Column("ci_id",        sa.String(36),  sa.ForeignKey("cmdb_items.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by",   sa.String(36),  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at",   sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at",   sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("ix_cmdb_agent_registrations_token_hash", "cmdb_agent_registrations", ["token_hash"])
    op.create_index("ix_cmdb_agent_registrations_ci_id",      "cmdb_agent_registrations", ["ci_id"])


def downgrade() -> None:
    op.drop_table("cmdb_agent_registrations")
