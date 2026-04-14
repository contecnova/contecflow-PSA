"""Add unique index to prevent duplicate imputation by user+task+date.

Revision ID: 021_imputation_unique_user_task_date
Revises: 020_tenant_scope_ai_providers_and_rate_tables
Create Date: 2026-04-14
"""
from alembic import op


revision = "021_imputation_unique_user_task_date"
down_revision = "020_tenant_scope_ai_providers_and_rate_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_imputations_user_task_date",
        "imputations",
        ["user_id", "task_id", "date"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_imputations_user_task_date", table_name="imputations")
