"""044 – ITSM-P08: formal KnownError -> affected Tickets links

Adds the missing relational link between Known Errors and affected incidents.

New table:
  sd_known_error_tickets
    known_error_id -> sd_known_errors.id
    ticket_id -> sd_tickets.id
    incident_link_id -> sd_incident_to_problem.id (optional provenance)

Revision ID: 044_known_error_ticket_links
Revises: 043_problem_mgmt_relational
Create Date: 2026-04-28
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "044_known_error_ticket_links"
down_revision = "043_problem_mgmt_relational"
branch_labels = None
depends_on = None


def _table_exists(table: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return table in insp.get_table_names()


def upgrade() -> None:
    if not _table_exists("sd_known_error_tickets"):
        op.create_table(
            "sd_known_error_tickets",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "known_error_id",
                sa.String(36),
                sa.ForeignKey("sd_known_errors.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column(
                "ticket_id",
                sa.String(36),
                sa.ForeignKey("sd_tickets.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column(
                "incident_link_id",
                sa.String(36),
                sa.ForeignKey("sd_incident_to_problem.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.UniqueConstraint("known_error_id", "ticket_id", name="uq_known_error_ticket"),
        )

    # Backfill from existing relations:
    # known_error (by problem_id) x incident_to_problem (same problem_id)
    if (
        _table_exists("sd_known_error_tickets")
        and _table_exists("sd_known_errors")
        and _table_exists("sd_incident_to_problem")
    ):
        bind = op.get_bind()
        try:
            bind.execute(sa.text(
                """
                INSERT INTO sd_known_error_tickets
                    (id, known_error_id, ticket_id, incident_link_id, created_at)
                SELECT
                    gen_random_uuid()::text,
                    ke.id,
                    ip.ticket_id,
                    ip.id,
                    COALESCE(ip.linked_at, NOW())
                FROM sd_known_errors ke
                JOIN sd_incident_to_problem ip
                  ON ip.problem_id = ke.problem_id
                ON CONFLICT (known_error_id, ticket_id) DO NOTHING
                """
            ))
        except Exception:
            # Fallback for environments without gen_random_uuid() or limited SQL features.
            pass


def downgrade() -> None:
    if _table_exists("sd_known_error_tickets"):
        op.drop_table("sd_known_error_tickets")
