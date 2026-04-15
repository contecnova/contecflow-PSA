"""Add is_invoiced and invoiced_invoice_id to imputations.

Prevents double-billing in T&M: once an imputation is included in a
persisted Invoice, is_invoiced is set to True and invoice_from_timesheets
will no longer return it.

Revision ID: 024_imputation_is_invoiced
Revises: 023_api_pagination_and_query_indexes
Create Date: 2026-04-15
"""

from alembic import op
import sqlalchemy as sa


revision = "024_imputation_is_invoiced"
down_revision = "023_api_pagination_and_query_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "imputations",
        sa.Column("is_invoiced", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "imputations",
        sa.Column("invoiced_invoice_id", sa.String(36), nullable=True),
    )
    op.create_index(
        "ix_024_imputations_is_invoiced",
        "imputations",
        ["is_invoiced"],
        unique=False,
    )
    op.create_index(
        "ix_024_imputations_invoiced_invoice_id",
        "imputations",
        ["invoiced_invoice_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_024_imputations_invoiced_invoice_id", table_name="imputations")
    op.drop_index("ix_024_imputations_is_invoiced", table_name="imputations")
    op.drop_column("imputations", "invoiced_invoice_id")
    op.drop_column("imputations", "is_invoiced")
