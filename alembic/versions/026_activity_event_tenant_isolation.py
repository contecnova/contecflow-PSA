"""026 — Add organization_id to activity_events for tenant isolation

ActivityEvent rows were not scoped to a tenant: the table had no
organization_id column so TenantSession could not automatically isolate
reads.  This migration adds the column and backfills it from the actor
user's organisation where possible.

Revision ID: 026_activity_event_tenant_isolation
Revises: 025_merge_multitenancy_heads
Create Date: 2026-04-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "026_activity_event_tenant_isolation"
down_revision = "025_merge_multitenancy_heads"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    return any(c["name"] == column for c in inspector.get_columns(table))


def _index_exists(table: str, index: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    return any(ix["name"] == index for ix in inspector.get_indexes(table))


def upgrade() -> None:
    # 1. Add nullable column (idempotent — skip if already present)
    if not _column_exists("activity_events", "organization_id"):
        op.add_column(
            "activity_events",
            sa.Column("organization_id", sa.String(36), nullable=True),
        )

    # 2. FK constraint — use batch mode for SQLite compatibility
    with op.batch_alter_table("activity_events") as batch_op:
        batch_op.create_foreign_key(
            "fk_activity_events_organization_id",
            "organizations",
            ["organization_id"], ["id"],
            ondelete="CASCADE",
        )

    # 3. Index for per-tenant feed queries (idempotent)
    if not _index_exists("activity_events", "ix_activity_events_organization_id"):
        op.create_index(
            "ix_activity_events_organization_id",
            "activity_events", ["organization_id"],
        )

    # 4. Backfill: derive org from the actor user where known
    op.execute(
        """
        UPDATE activity_events
        SET organization_id = (
            SELECT users.organization_id
            FROM users
            WHERE users.id = activity_events.actor_id
              AND users.organization_id IS NOT NULL
            LIMIT 1
        )
        WHERE organization_id IS NULL
          AND actor_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_activity_events_organization_id", table_name="activity_events")
    op.drop_constraint(
        "fk_activity_events_organization_id", "activity_events", type_="foreignkey"
    )
    op.drop_column("activity_events", "organization_id")
