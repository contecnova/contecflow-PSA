"""Service Desk AI governance tables (offline eval + drift by tenant).

Revision ID: 037_sd_ai_governance_tables
Revises: 036_kb_article_versions
Create Date: 2026-04-27
"""
from alembic import op
import sqlalchemy as sa

revision = "037_sd_ai_governance_tables"
down_revision = "036_kb_article_versions"
branch_labels = None
depends_on = None


def _table_exists(table: str) -> bool:
    """Return True when table already exists (defensive upgrade)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table in inspector.get_table_names()


def upgrade() -> None:
    if not _table_exists("sd_ai_evaluation_runs"):
        op.create_table(
            "sd_ai_evaluation_runs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True),
            sa.Column("model_name", sa.String(120), nullable=False),
            sa.Column("task_type", sa.String(50), nullable=False),
            sa.Column("dataset_name", sa.String(120), nullable=True),
            sa.Column("status", sa.String(20), server_default="completed"),
            sa.Column("score", sa.String(20), nullable=True),
            sa.Column("metrics_json", sa.Text(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_sd_ai_evaluation_runs_org", "sd_ai_evaluation_runs", ["organization_id"])

    if not _table_exists("sd_ai_drift_snapshots"):
        op.create_table(
            "sd_ai_drift_snapshots",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True),
            sa.Column("model_name", sa.String(120), nullable=False),
            sa.Column("feature_set", sa.String(120), nullable=False, server_default="default"),
            sa.Column("drift_score", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(20), server_default="ok"),
            sa.Column("details_json", sa.Text(), nullable=True),
            sa.Column("measured_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_sd_ai_drift_snapshots_org", "sd_ai_drift_snapshots", ["organization_id"])
        op.create_index("ix_sd_ai_drift_snapshots_measured", "sd_ai_drift_snapshots", ["measured_at"])


def downgrade() -> None:
    op.drop_index("ix_sd_ai_drift_snapshots_measured", table_name="sd_ai_drift_snapshots")
    op.drop_index("ix_sd_ai_drift_snapshots_org", table_name="sd_ai_drift_snapshots")
    op.drop_table("sd_ai_drift_snapshots")
    op.drop_index("ix_sd_ai_evaluation_runs_org", table_name="sd_ai_evaluation_runs")
    op.drop_table("sd_ai_evaluation_runs")
