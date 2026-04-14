"""015 — multi-tenant org isolation: add organization_id to projects

Adds organisation-level row isolation to the projects table so that every
project belongs to exactly one tenant.  The column is nullable during the
migration to avoid breaking existing data; a backfill step promotes every
project whose PM belongs to an organisation.

Revision ID: 015_multitenant_org_isolation
Revises: 014_ai_providers
Create Date: 2025-01-01 00:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "015_multitenant_org_isolation"
down_revision = "014_ai_providers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add the nullable column
    op.add_column(
        "projects",
        sa.Column("organization_id", sa.String(36), nullable=True),
    )

    # 2. Create FK constraint (deferred so existing rows remain valid)
    op.create_foreign_key(
        "fk_projects_organization_id",
        "projects", "organizations",
        ["organization_id"], ["id"],
        ondelete="SET NULL",
    )

    # 3. Create index for fast per-tenant queries
    op.create_index(
        "ix_projects_organization_id",
        "projects", ["organization_id"],
    )

    # 4. Backfill: assign projects to the PM's organisation where known
    op.execute(
        """
        UPDATE projects
        SET organization_id = (
            SELECT users.organization_id
            FROM users
            WHERE users.id = projects.pm_id
              AND users.organization_id IS NOT NULL
            LIMIT 1
        )
        WHERE organization_id IS NULL
          AND pm_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_projects_organization_id", table_name="projects")
    op.drop_constraint("fk_projects_organization_id", "projects", type_="foreignkey")
    op.drop_column("projects", "organization_id")
