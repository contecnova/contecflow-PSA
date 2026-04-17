"""028 — Add SLA metric columns to sd_tickets

Adds first_response_minutes, resolution_minutes, sla_response_breached
and sla_resolution_breached to the sd_tickets table.  These columns are
defined in the Ticket SQLAlchemy model but were missing from the database,
causing 500 errors on every /sd/tickets request.

Revision ID: 028_sd_tickets_sla_metrics
Revises: 027_approval_step_started_at
Create Date: 2026-04-17
"""
from alembic import op
import sqlalchemy as sa

revision = "028_sd_tickets_sla_metrics"
down_revision = "027_approval_step_started_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    existing = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(sd_tickets)"))}
    if "first_response_minutes" not in existing:
        op.execute(sa.text("ALTER TABLE sd_tickets ADD COLUMN first_response_minutes INTEGER"))
    if "resolution_minutes" not in existing:
        op.execute(sa.text("ALTER TABLE sd_tickets ADD COLUMN resolution_minutes INTEGER"))
    if "sla_response_breached" not in existing:
        op.execute(sa.text("ALTER TABLE sd_tickets ADD COLUMN sla_response_breached BOOLEAN DEFAULT 0"))
    if "sla_resolution_breached" not in existing:
        op.execute(sa.text("ALTER TABLE sd_tickets ADD COLUMN sla_resolution_breached BOOLEAN DEFAULT 0"))


def downgrade() -> None:
    # SQLite does not support DROP COLUMN in older versions; no-op is safe here.
    pass
