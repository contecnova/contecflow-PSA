"""039 – ITSM-P02: Problem KEDB lifecycle + RCA approval fields

Adds to sd_problems:
  - investigation_started_at   — when RCA investigation began
  - rca_due_date               — SLA deadline for completing RCA
  - rca_evidence               — JSON/text evidence supporting root cause
  - rca_approved_by            — user id who approved the RCA
  - rca_approved_at            — timestamp of RCA approval
  - kedb_published_at          — when problem was promoted to Known Error DB
  - kedb_expires_at            — review / expiry date for the KEDB entry
  - kedb_reviewed_at           — last manual review of the KEDB entry
  - kedb_effectiveness_score   — 0-100, % of linked tickets resolved via workaround
  - kb_article_id              — FK to auto-generated KB article on resolution

Revision ID: 039_itsm_problem_kedb
Revises: 038_ai_auto_resolution
Create Date: 2026-04-28
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "039_itsm_problem_kedb"
down_revision = "038_ai_auto_resolution"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return column in [c["name"] for c in inspector.get_columns(table)]


def upgrade() -> None:
    new_columns = [
        ("investigation_started_at",  sa.DateTime(timezone=True), {"nullable": True}),
        ("rca_due_date",              sa.DateTime(timezone=True), {"nullable": True}),
        ("rca_evidence",              sa.Text(),                  {"nullable": True}),
        ("rca_approved_by",           sa.String(36),              {"nullable": True}),
        ("rca_approved_at",           sa.DateTime(timezone=True), {"nullable": True}),
        ("kedb_published_at",         sa.DateTime(timezone=True), {"nullable": True}),
        ("kedb_expires_at",           sa.DateTime(timezone=True), {"nullable": True}),
        ("kedb_reviewed_at",          sa.DateTime(timezone=True), {"nullable": True}),
        ("kedb_effectiveness_score",  sa.Float(),                 {"nullable": True}),
        ("kb_article_id",             sa.String(36),              {"nullable": True}),
    ]
    for col_name, col_type, kwargs in new_columns:
        if not _column_exists("sd_problems", col_name):
            op.add_column("sd_problems", sa.Column(col_name, col_type, **kwargs))


def downgrade() -> None:
    for col_name in [
        "investigation_started_at",
        "rca_due_date",
        "rca_evidence",
        "rca_approved_by",
        "rca_approved_at",
        "kedb_published_at",
        "kedb_expires_at",
        "kedb_reviewed_at",
        "kedb_effectiveness_score",
        "kb_article_id",
    ]:
        if _column_exists("sd_problems", col_name):
            op.drop_column("sd_problems", col_name)
