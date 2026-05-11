"""Organization.require_mfa policy flag

Revision ID: 074_org_require_mfa
Revises: 073_fk_indexes
Create Date: 2026-05-11
"""
from alembic import op
import sqlalchemy as sa


revision = "074_org_require_mfa"
down_revision = "073_fk_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("organizations")}
    if "require_mfa" not in cols:
        op.add_column(
            "organizations",
            sa.Column("require_mfa", sa.Boolean, nullable=False, server_default="0"),
        )


def downgrade() -> None:
    op.drop_column("organizations", "require_mfa")
