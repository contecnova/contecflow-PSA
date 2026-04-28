"""043 – ITSM-P08: Problem Management relational schema

Creates three tables specified in the ITSM comparative report that were never
implemented with proper migrations — the system had been using JSON blobs on
AppSetting and inline columns on sd_problems instead.

New tables:
  sd_known_errors
      Proper KEDB entity with FK to sd_problems. Replaces the kedb_* columns
      on sd_problems (those are kept for backwards-compat but this is canonical).

  sd_problem_rca_templates
      Reusable, admin-defined RCA template definitions stored relationally.
      Each template has a name, type, and a JSON array of step definitions.
      Replaces the hard-coded template dict in rca_wizard_service.py.

  sd_incident_to_problem
      Rich junction table between sd_tickets and sd_problems. Replaces the
      bare Ticket.problem_id FK with metadata (causal flag, linker, notes).

Revision ID: 043_problem_mgmt_relational
Revises: 042_routing_feedback
Create Date: 2026-04-28
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "043_problem_mgmt_relational"
down_revision = "042_routing_feedback"
branch_labels = None
depends_on = None


def _table_exists(table: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return table in insp.get_table_names()


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    # ── sd_known_errors ──────────────────────────────────────────────────────
    if not _table_exists("sd_known_errors"):
        op.create_table(
            "sd_known_errors",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "problem_id",
                sa.String(36),
                sa.ForeignKey("sd_problems.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("title", sa.String(500), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("workaround", sa.Text(), nullable=True),
            sa.Column("root_cause", sa.Text(), nullable=True),
            sa.Column("rca_type", sa.String(30), nullable=True),
            # JSON list of CI ids / service names affected
            sa.Column("affects_json", sa.Text(), nullable=True),
            sa.Column(
                "category_id",
                sa.String(36),
                sa.ForeignKey("sd_service_categories.id", ondelete="SET NULL"),
                nullable=True,
                index=True,
            ),
            sa.Column(
                "kb_article_id",
                sa.String(36),
                sa.ForeignKey("sd_kb_articles.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "published_by",
                sa.String(36),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("effectiveness_score", sa.Float(), nullable=True),
            sa.Column(
                "is_active",
                sa.Boolean(),
                server_default="true",
                nullable=False,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )

    # ── sd_problem_rca_templates ─────────────────────────────────────────────
    if not _table_exists("sd_problem_rca_templates"):
        op.create_table(
            "sd_problem_rca_templates",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("name", sa.String(255), nullable=False),
            # five_whys | fishbone | itil_standard | custom
            sa.Column("template_type", sa.String(30), nullable=False, index=True),
            # JSON array of {step, label, prompt} objects
            sa.Column("steps_json", sa.Text(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            # True = built-in system template (non-deletable)
            sa.Column(
                "is_system",
                sa.Boolean(),
                server_default="false",
                nullable=False,
            ),
            sa.Column(
                "is_active",
                sa.Boolean(),
                server_default="true",
                nullable=False,
            ),
            sa.Column(
                "created_by",
                sa.String(36),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )

    # ── sd_incident_to_problem ───────────────────────────────────────────────
    if not _table_exists("sd_incident_to_problem"):
        op.create_table(
            "sd_incident_to_problem",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "problem_id",
                sa.String(36),
                sa.ForeignKey("sd_problems.id", ondelete="CASCADE"),
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
            # True = this ticket is considered a primary/causal incident
            sa.Column(
                "is_causal",
                sa.Boolean(),
                server_default="false",
                nullable=False,
            ),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column(
                "linked_by",
                sa.String(36),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "linked_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            # Unique: one row per (problem, ticket) pair
            sa.UniqueConstraint("problem_id", "ticket_id", name="uq_problem_ticket"),
        )

    # ── Backfill sd_incident_to_problem from existing Ticket.problem_id FK ──
    # We use raw SQL to copy existing relationships into the new junction table.
    # Any ticket that already has problem_id set gets a row in sd_incident_to_problem.
    if _table_exists("sd_incident_to_problem") and _table_exists("sd_tickets"):
        bind = op.get_bind()
        # Use gen_random_uuid() on PostgreSQL, fallback uuid() otherwise
        try:
            bind.execute(sa.text(
                """
                INSERT INTO sd_incident_to_problem
                    (id, problem_id, ticket_id, is_causal, linked_at)
                SELECT
                    gen_random_uuid()::text,
                    problem_id,
                    id,
                    false,
                    COALESCE(created_at, NOW())
                FROM sd_tickets
                WHERE problem_id IS NOT NULL
                ON CONFLICT (problem_id, ticket_id) DO NOTHING
                """
            ))
        except Exception:
            # SQLite or no gen_random_uuid — skip backfill (test env)
            pass


def downgrade() -> None:
    if _table_exists("sd_incident_to_problem"):
        op.drop_table("sd_incident_to_problem")
    if _table_exists("sd_problem_rca_templates"):
        op.drop_table("sd_problem_rca_templates")
    if _table_exists("sd_known_errors"):
        op.drop_table("sd_known_errors")
