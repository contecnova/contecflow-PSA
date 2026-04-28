"""042 – ML Routing Feedback table

Records routing outcomes per ticket so the ML scoring can learn from
historical agent performance (resolution speed, CSAT, reopens) broken
down by ticket_type × category × priority bucket.

New table: sd_routing_feedback
  id                  — UUID PK
  ticket_id           — FK sd_tickets (nullable after ticket deletion)
  assigned_agent_id   — FK users (nullable after user deletion)
  ticket_type         — str  (incident|service_request|change|problem|question)
  category_id         — str  FK sd_service_categories (nullable)
  priority            — str  (p1_critical|p2_high|p3_medium|p4_low)
  support_level       — str  (l1|l2|l3)
  resolution_minutes  — int  nullable  (filled when ticket closes)
  csat_score          — int  nullable  (1-5, filled when CSAT submitted)
  reopened            — bool default false
  routed_at           — timestamp (when routing decision was made)
  outcome_recorded_at — timestamp (when resolution outcome was captured)

Revision ID: 042_routing_feedback
Revises: 041_rca_wizard
Create Date: 2026-04-28
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "042_routing_feedback"
down_revision = "041_rca_wizard"
branch_labels = None
depends_on = None


def _table_exists(table: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return table in insp.get_table_names()


def upgrade() -> None:
    if not _table_exists("sd_routing_feedback"):
        op.create_table(
            "sd_routing_feedback",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "ticket_id",
                sa.String(36),
                sa.ForeignKey("sd_tickets.id", ondelete="SET NULL"),
                nullable=True,
                index=True,
            ),
            sa.Column(
                "assigned_agent_id",
                sa.String(36),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
                index=True,
            ),
            sa.Column("ticket_type", sa.String(30), nullable=True, index=True),
            sa.Column(
                "category_id",
                sa.String(36),
                sa.ForeignKey("sd_service_categories.id", ondelete="SET NULL"),
                nullable=True,
                index=True,
            ),
            sa.Column("priority", sa.String(20), nullable=True),
            sa.Column("support_level", sa.String(10), nullable=True),
            sa.Column("resolution_minutes", sa.Integer(), nullable=True),
            sa.Column("csat_score", sa.Integer(), nullable=True),
            sa.Column("reopened", sa.Boolean(), server_default="false", nullable=False),
            sa.Column(
                "routed_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("outcome_recorded_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    if _table_exists("sd_routing_feedback"):
        op.drop_table("sd_routing_feedback")
