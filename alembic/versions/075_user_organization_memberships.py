"""Add user_organization_memberships table for multi-org users

Revision ID: 075_user_organization_memberships
Revises: 074_org_require_mfa
Create Date: 2026-05-12
"""

from alembic import op
import sqlalchemy as sa

import uuid


revision = "075_user_organization_memberships"
down_revision = "074_org_require_mfa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if "user_organization_memberships" not in insp.get_table_names():
        op.create_table(
            "user_organization_memberships",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("organization_id", sa.String(length=36), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", "organization_id", name="uq_user_org_membership"),
        )
        op.create_index(op.f("ix_user_organization_memberships_user_id"), "user_organization_memberships", ["user_id"], unique=False)
        op.create_index(op.f("ix_user_organization_memberships_organization_id"), "user_organization_memberships", ["organization_id"], unique=False)

    rows = bind.execute(sa.text("SELECT id, organization_id FROM users WHERE organization_id IS NOT NULL")).fetchall()
    for row in rows:
        user_id = str(row[0])
        org_id = str(row[1])
        exists = bind.execute(
            sa.text(
                "SELECT 1 FROM user_organization_memberships "
                "WHERE user_id = :user_id AND organization_id = :org_id"
            ),
            {"user_id": user_id, "org_id": org_id},
        ).first()
        if exists:
            continue
        bind.execute(
            sa.text(
                "INSERT INTO user_organization_memberships (id, user_id, organization_id) "
                "VALUES (:id, :user_id, :org_id)"
            ),
            {"id": str(uuid.uuid4()), "user_id": user_id, "org_id": org_id},
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "user_organization_memberships" in insp.get_table_names():
        op.drop_index(op.f("ix_user_organization_memberships_organization_id"), table_name="user_organization_memberships")
        op.drop_index(op.f("ix_user_organization_memberships_user_id"), table_name="user_organization_memberships")
        op.drop_table("user_organization_memberships")
