"""workflow runtime tables (runs + steps)

Revision ID: 060_workflow_runtime
Revises: 001_initial_tables
Create Date: 2026-05-09
"""
from alembic import op
import sqlalchemy as sa


revision = "060_workflow_runtime"
down_revision = "001_initial_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if "sd_workflow_runs" not in insp.get_table_names():
        op.create_table(
            "sd_workflow_runs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True),
            sa.Column("blueprint_id", sa.String(36), sa.ForeignKey("sd_workflow_blueprints.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("blueprint_version_id", sa.String(36), sa.ForeignKey("sd_workflow_blueprint_versions.id", ondelete="SET NULL"), nullable=True),
            sa.Column("blueprint_version", sa.Integer, nullable=False),
            sa.Column("target_entity_type", sa.String(40), nullable=True),
            sa.Column("target_entity_id", sa.String(36), nullable=True, index=True),
            sa.Column(
                "status",
                sa.Enum("running", "waiting", "completed", "cancelled", "error", name="workflowrunstatus"),
                nullable=False,
                server_default="running",
                index=True,
            ),
            sa.Column("current_node_id", sa.String(120), nullable=True),
            sa.Column("wake_at", sa.DateTime(timezone=True), nullable=True, index=True),
            sa.Column("last_error", sa.Text, nullable=True),
            sa.Column("context_json", sa.JSON, nullable=False),
            sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_sd_workflow_runs_blueprint_status", "sd_workflow_runs", ["blueprint_id", "status"])

    if "sd_workflow_run_steps" not in insp.get_table_names():
        op.create_table(
            "sd_workflow_run_steps",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("run_id", sa.String(36), sa.ForeignKey("sd_workflow_runs.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("node_id", sa.String(120), nullable=False),
            sa.Column("node_type", sa.String(40), nullable=False),
            sa.Column(
                "status",
                sa.Enum("done", "waiting", "error", name="workflowrunstepstatus"),
                nullable=False,
                server_default="done",
            ),
            sa.Column("branch_taken", sa.String(40), nullable=True),
            sa.Column("payload_json", sa.JSON, nullable=False),
            sa.Column("error", sa.Text, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    op.drop_table("sd_workflow_run_steps")
    op.drop_index("ix_sd_workflow_runs_blueprint_status", table_name="sd_workflow_runs")
    op.drop_table("sd_workflow_runs")
    sa.Enum(name="workflowrunstepstatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="workflowrunstatus").drop(op.get_bind(), checkfirst=True)
