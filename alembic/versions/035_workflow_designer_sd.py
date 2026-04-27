"""Service Desk visual workflow designer tables.

Revision ID: 035_workflow_designer_sd
Revises: 034_jira_integration
Create Date: 2026-04-27
"""
from alembic import op
import sqlalchemy as sa

revision = "035_workflow_designer_sd"
down_revision = "034_jira_integration"
branch_labels = None
depends_on = None


def _table_exists(table: str) -> bool:
    """Return True when table already exists (defensive upgrade)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table in inspector.get_table_names()


def upgrade() -> None:
    if not _table_exists("sd_workflow_blueprints"):
        op.create_table(
            "sd_workflow_blueprints",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("description", sa.String(500), nullable=True),
            sa.Column("process_type", sa.String(50), nullable=False),
            sa.Column("scope", sa.String(30), server_default="global"),
            sa.Column("latest_version", sa.Integer(), server_default="1"),
            sa.Column("status", sa.String(20), server_default="draft"),
            sa.Column("is_active", sa.Boolean(), server_default="1"),
            sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_sd_workflow_blueprints_process_type", "sd_workflow_blueprints", ["process_type"])

    if not _table_exists("sd_workflow_blueprint_versions"):
        op.create_table(
            "sd_workflow_blueprint_versions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("blueprint_id", sa.String(36), sa.ForeignKey("sd_workflow_blueprints.id", ondelete="CASCADE"), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("graph_json", sa.Text(), nullable=False),
            sa.Column("rules_json", sa.Text(), nullable=True),
            sa.Column("is_published", sa.Boolean(), server_default="0"),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_sd_workflow_blueprint_versions_blueprint_id", "sd_workflow_blueprint_versions", ["blueprint_id"])


def downgrade() -> None:
    op.drop_index("ix_sd_workflow_blueprint_versions_blueprint_id", table_name="sd_workflow_blueprint_versions")
    op.drop_table("sd_workflow_blueprint_versions")
    op.drop_index("ix_sd_workflow_blueprints_process_type", table_name="sd_workflow_blueprints")
    op.drop_table("sd_workflow_blueprints")
