"""Allow forced duplicate timer imputations.

Revision ID: 049_drop_imputation_unique_index_for_forced_timer_overrides
Revises: 048_task_movement_log
Create Date: 2026-05-02
"""
from __future__ import annotations

from alembic import op


revision = "049_drop_imputation_unique_index_for_forced_timer_overrides"
down_revision = "048_task_movement_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("uq_imputations_user_task_date", table_name="imputations")


def downgrade() -> None:
    op.create_index(
        "uq_imputations_user_task_date",
        "imputations",
        ["user_id", "task_id", "date"],
        unique=True,
    )