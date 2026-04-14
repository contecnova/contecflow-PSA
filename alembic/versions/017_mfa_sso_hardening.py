"""017 - MFA replay protection and SSO tenant binding

Revision ID: 017_mfa_sso_hardening
Revises: 016_task_status_in_review
Create Date: 2026-04-12 00:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "017_mfa_sso_hardening"
down_revision = "016_task_status_in_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mfa_challenges",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("token_jti", sa.String(length=36), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_jti"),
    )
    op.create_index("ix_mfa_challenges_user_id", "mfa_challenges", ["user_id"])
    op.create_index("ix_mfa_challenges_expires_at", "mfa_challenges", ["expires_at"])
    op.create_index("ix_mfa_challenges_consumed_at", "mfa_challenges", ["consumed_at"])

    op.add_column("sso_configs", sa.Column("organization_id", sa.String(length=36), nullable=True))
    op.create_foreign_key(
        "fk_sso_configs_organization_id",
        "sso_configs",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_sso_configs_organization_id", "sso_configs", ["organization_id"])

    op.execute(
        """
        UPDATE sso_configs
        SET organization_id = (
            SELECT id FROM organizations ORDER BY created_at ASC LIMIT 1
        )
        WHERE organization_id IS NULL
          AND (SELECT COUNT(*) FROM organizations) = 1
        """
    )


def downgrade() -> None:
    op.drop_index("ix_sso_configs_organization_id", table_name="sso_configs")
    op.drop_constraint("fk_sso_configs_organization_id", "sso_configs", type_="foreignkey")
    op.drop_column("sso_configs", "organization_id")

    op.drop_index("ix_mfa_challenges_consumed_at", table_name="mfa_challenges")
    op.drop_index("ix_mfa_challenges_expires_at", table_name="mfa_challenges")
    op.drop_index("ix_mfa_challenges_user_id", table_name="mfa_challenges")
    op.drop_table("mfa_challenges")
