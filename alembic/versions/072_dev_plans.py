"""Development plans + goals (plan de acción tras 360°)

Revision ID: 072_dev_plans
Revises: 071_perf_360_campaigns
Create Date: 2026-05-10
"""
from alembic import op
import sqlalchemy as sa


revision = "072_dev_plans"
down_revision = "071_perf_360_campaigns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if "development_plans" not in insp.get_table_names():
        op.create_table(
            "development_plans",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("subject_id", sa.String(36),
                      sa.ForeignKey("users.id"),
                      nullable=False, index=True),
            sa.Column("campaign_id", sa.String(36),
                      sa.ForeignKey("review_360_campaigns.id",
                                    ondelete="SET NULL"),
                      nullable=True, index=True),
            sa.Column("cycle_id", sa.String(36),
                      sa.ForeignKey("review_cycles.id", ondelete="SET NULL"),
                      nullable=True, index=True),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("summary", sa.Text, nullable=True),
            sa.Column(
                "status",
                sa.Enum("draft", "active", "completed", "archived",
                        name="devplanstatus"),
                nullable=False, server_default="draft",
            ),
            sa.Column("target_date", sa.Date, nullable=True),
            sa.Column("next_review_at", sa.Date, nullable=True),
            sa.Column("created_by", sa.String(36),
                      sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )

    if "dev_goals" not in insp.get_table_names():
        op.create_table(
            "dev_goals",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("plan_id", sa.String(36),
                      sa.ForeignKey("development_plans.id", ondelete="CASCADE"),
                      nullable=False, index=True),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("description", sa.Text, nullable=True),
            sa.Column(
                "status",
                sa.Enum("pending", "in_progress", "done", "blocked", "cancelled",
                        name="devgoalstatus"),
                nullable=False, server_default="pending",
            ),
            sa.Column("due_date", sa.Date, nullable=True),
            sa.Column("progress", sa.Integer, nullable=False, server_default="0"),
            sa.Column("order", sa.Integer, nullable=False, server_default="0"),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    op.drop_table("dev_goals")
    op.drop_table("development_plans")
    sa.Enum(name="devgoalstatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="devplanstatus").drop(op.get_bind(), checkfirst=True)
