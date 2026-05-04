"""approval_engine_v2_enterprise

Revision ID: 060_approval_engine_v2
Revises: 050_doc_approval_wf
Create Date: 2026-05-03
"""
from alembic import op
import sqlalchemy as sa

revision = '060_approval_engine_v2'
down_revision = '050_doc_approval_wf'
branch_labels = None
depends_on = None


def upgrade():
    # ── approval_steps: new enterprise fields ──────────────────────────────────
    with op.batch_alter_table("approval_steps") as batch:
        batch.add_column(sa.Column("parallel_quorum", sa.Boolean(), server_default="0", nullable=False))
        batch.add_column(sa.Column("required_approvals", sa.Integer(), server_default="1", nullable=False))
        batch.add_column(sa.Column("step_condition", sa.Text(), nullable=True))
        batch.add_column(sa.Column("requires_attachment", sa.Boolean(), server_default="0", nullable=False))
        batch.add_column(sa.Column("reminder_hours", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("approver_group_id", sa.String(36), nullable=True))

    # ── approval_workflows: chaining + SLA block + auto-rules ────────────────
    with op.batch_alter_table("approval_workflows") as batch:
        batch.add_column(sa.Column("chain_on_approval_workflow_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("sla_block_on_breach", sa.Boolean(), server_default="0", nullable=False))
        batch.add_column(sa.Column("auto_approval_rules", sa.Text(), nullable=True))

    # ── approval_decisions: optional attachment ────────────────────────────────
    with op.batch_alter_table("approval_decisions") as batch:
        batch.add_column(sa.Column("attachment_url", sa.Text(), nullable=True))

    # ── approval_groups ────────────────────────────────────────────────────────
    op.create_table(
        "approval_groups",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("member_ids", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("approval_groups")

    with op.batch_alter_table("approval_decisions") as batch:
        batch.drop_column("attachment_url")

    with op.batch_alter_table("approval_workflows") as batch:
        batch.drop_column("auto_approval_rules")
        batch.drop_column("sla_block_on_breach")
        batch.drop_column("chain_on_approval_workflow_id")

    with op.batch_alter_table("approval_steps") as batch:
        batch.drop_column("approver_group_id")
        batch.drop_column("reminder_hours")
        batch.drop_column("requires_attachment")
        batch.drop_column("step_condition")
        batch.drop_column("required_approvals")
        batch.drop_column("parallel_quorum")
