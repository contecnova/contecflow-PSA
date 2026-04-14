"""016 — add in_review to TaskStatus enum and migrate existing 'review' rows

Adds in_review as the canonical frontend-facing status value.
Existing 'review' rows are migrated to 'in_review'.
The 'review' enum value is kept for backward compatibility.

Revision ID: 016_task_status_in_review
Revises: 015_multitenant_org_isolation
Create Date: 2026-04-11
"""
from alembic import op
import sqlalchemy as sa

revision = "016_task_status_in_review"
down_revision = "015_multitenant_org_isolation"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    dialect = conn.dialect.name

    if dialect == "postgresql":
        # PostgreSQL: add enum value then migrate data
        op.execute("ALTER TYPE taskstatus ADD VALUE IF NOT EXISTS 'in_review' BEFORE 'review'")
        op.execute("UPDATE tasks SET status = 'in_review' WHERE status = 'review'")
    else:
        # SQLite: just update the data (no ALTER TYPE needed)
        op.execute("UPDATE tasks SET status = 'in_review' WHERE status = 'review'")


def downgrade():
    conn = op.get_bind()
    # Revert in_review back to review
    op.execute("UPDATE tasks SET status = 'review' WHERE status = 'in_review'")
    # Note: PostgreSQL does not support removing enum values — the 'in_review' label stays
    # in the type definition but will have no rows. SQLite has no enum type to alter.
