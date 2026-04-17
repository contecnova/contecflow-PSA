"""027 — Add step_started_at to approval_requests for timeout tracking

approval_requests had no way to know when the current step became active,
so timeout_hours on ApprovalStep could never be enforced.  This column
tracks when each step started; the hourly Celery job uses it to detect
overdue steps and apply the configured on_timeout action.

Revision ID: 027_approval_step_started_at
Revises: 026_activity_event_tenant_isolation
Create Date: 2026-04-17
"""
from alembic import op
import sqlalchemy as sa

revision = "027_approval_step_started_at"
down_revision = "026_activity_event_tenant_isolation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "approval_requests",
        sa.Column("step_started_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Backfill: for all existing pending requests use created_at as the step start
    # (conservative — avoids immediate spurious timeouts on first deploy)
    op.execute(
        """
        UPDATE approval_requests
        SET step_started_at = created_at
        WHERE status = 'pending' AND step_started_at IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("approval_requests", "step_started_at")
