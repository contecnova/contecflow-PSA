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

revision = "026_activity_event_tenant_isolation"
down_revision = "025_merge_multitenancy_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add nullable column (existing rows will be NULL, backfilled below)
    op.add_column(
        "activity_events",
        sa.Column("organization_id", sa.String(36), nullable=True),
    )

    # 2. FK constraint — deferred so existing NULL rows stay valid
    op.create_foreign_key(
        "fk_activity_events_organization_id",
        "activity_events", "organizations",
        ["organization_id"], ["id"],
        ondelete="CASCADE",
    )

    # 3. Index for per-tenant feed queries
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
