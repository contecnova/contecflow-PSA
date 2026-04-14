"""Add SCIM fields, policy packs and compliance evidence tables

Revision ID: 008_governance_scim_policy_compliance
Revises: 007_user_sessions_panel
Create Date: 2026-04-07
"""
from alembic import op
import sqlalchemy as sa

revision = "008_governance_scim_policy_compliance"
down_revision = "007_user_sessions_panel"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("scim_external_id", sa.String(255), nullable=True))
        batch_op.add_column(sa.Column("scim_last_synced_at", sa.DateTime(timezone=True), nullable=True))

    op.create_index("ix_users_scim_external_id", "users", ["scim_external_id"], unique=False)

    op.create_table(
        "tenant_policy_packs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False, index=True),
        sa.Column("pack_key", sa.String(80), nullable=False, index=True),
        sa.Column("pack_version", sa.String(20), nullable=False, server_default="1.0"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("config_json", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.String(36), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
    )

    op.create_table(
        "compliance_evidence",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False, index=True),
        sa.Column("framework", sa.String(30), nullable=False, index=True),
        sa.Column("control_id", sa.String(50), nullable=False, index=True),
        sa.Column("evidence_type", sa.String(30), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("artifact_uri", sa.String(1000), nullable=True),
        sa.Column("artifact_hash", sa.String(128), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
    )


def downgrade():
    op.drop_table("compliance_evidence")
    op.drop_table("tenant_policy_packs")
    op.drop_index("ix_users_scim_external_id", table_name="users")
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("scim_last_synced_at")
        batch_op.drop_column("scim_external_id")
