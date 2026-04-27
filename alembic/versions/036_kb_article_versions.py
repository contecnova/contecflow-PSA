"""Add KB article versioning for audit and rollback.

Revision ID: 036_kb_article_versions
Revises: 035_workflow_designer_sd
Create Date: 2026-04-27
"""
from alembic import op
import sqlalchemy as sa

revision = "036_kb_article_versions"
down_revision = "035_workflow_designer_sd"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sd_kb_article_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("article_id", sa.String(36), sa.ForeignKey("sd_kb_articles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("summary", sa.String(500), nullable=True),
        sa.Column("tags", sa.String(500), nullable=True),
        sa.Column("status", sa.String(20), nullable=True),
        sa.Column("change_note", sa.String(255), nullable=True),
        sa.Column("changed_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_sd_kb_article_versions_article_id", "sd_kb_article_versions", ["article_id"])


def downgrade() -> None:
    op.drop_index("ix_sd_kb_article_versions_article_id", table_name="sd_kb_article_versions")
    op.drop_table("sd_kb_article_versions")
