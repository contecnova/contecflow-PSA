"""041 – ITSM-P06: RCA Wizard — guided multi-step RCA with templates

Adds to sd_problems:
  - rca_template     — active template: five_whys|fishbone|itil_standard|custom
  - rca_wizard_state — JSON blob storing wizard steps, answers, and completion state

Revision ID: 041_rca_wizard
Revises: 040_cmdb_drift_detection
Create Date: 2026-04-28
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "041_rca_wizard"
down_revision = "040_cmdb_drift_detection"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return any(c["name"] == column for c in insp.get_columns(table))


def _table_exists(table: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return table in insp.get_table_names()


def upgrade() -> None:
    if _table_exists("sd_problems"):
        if not _column_exists("sd_problems", "rca_template"):
            op.add_column(
                "sd_problems",
                sa.Column("rca_template", sa.String(30), nullable=True),
            )
        if not _column_exists("sd_problems", "rca_wizard_state"):
            op.add_column(
                "sd_problems",
                sa.Column("rca_wizard_state", sa.Text(), nullable=True),
            )


def downgrade() -> None:
    if _table_exists("sd_problems"):
        if _column_exists("sd_problems", "rca_wizard_state"):
            op.drop_column("sd_problems", "rca_wizard_state")
        if _column_exists("sd_problems", "rca_template"):
            op.drop_column("sd_problems", "rca_template")
