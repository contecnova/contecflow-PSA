"""Store monetary columns as exact NUMERIC instead of Float.

Money was modelled as Float (IEEE-754), which drifts in storage and aggregation
(SUM) — unacceptable for invoicing, tax, FX and revenue recognition. This
migrates the monetary columns to NUMERIC(18,2) (amounts/totals) and
NUMERIC(18,6) (rates / FX / hourly rates) so PostgreSQL stores and aggregates
them exactly.

No-op on SQLite (used only by the test suite, which builds the schema from the
models directly and where NUMERIC maps to the same affinity as Float).

Revision ID: 087_money_numeric_precision
Revises: 086_org_scim_token_hash
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "087_money_numeric_precision"
down_revision: Union[str, None] = "086_org_scim_token_hash"
branch_labels = None
depends_on = None

# (table, column, scale) — precision is fixed at 18.
_AMOUNTS = [
    ("expenses", "amount"),
    ("imputations", "cost_amount"),
    ("clients", "credit_limit"),
    ("contracts", "monthly_retainer"),
    ("contracts", "total_amount"),
    ("invoice_lines", "amount"),
    ("invoice_lines", "unit_price"),
    ("invoices", "subtotal"),
    ("invoices", "tax_amount"),
    ("invoices", "total"),
    ("opportunities", "expected_revenue"),
    ("project_milestones", "billing_amount"),
    ("recurring_invoices", "amount"),
    ("revenue_recognition_entries", "amount_actual"),
    ("revenue_recognition_entries", "amount_deferred"),
    ("revenue_recognition_entries", "amount_planned"),
    ("revenue_recognition_entries", "cumulative_amount"),
    ("revenue_recognition_rules", "contract_value"),
    ("risks", "cost_impact_max"),
    ("risks", "cost_impact_min"),
    ("timesheets", "total_cost"),
    ("work_orders", "amount"),
]
_RATES = [
    ("imputations", "hourly_rate_snapshot"),
    ("contracts", "hourly_rate"),
    ("exchange_rates", "rate"),
    ("opportunities", "hourly_rate"),
    ("rate_entries", "billing_rate"),
    ("rate_entries", "cost_rate"),
    ("rate_overrides", "billing_rate"),
]


def _alter(table: str, column: str, scale: int) -> None:
    op.alter_column(
        table, column,
        type_=sa.Numeric(18, scale),
        existing_type=sa.Float(),
        postgresql_using=f"{column}::numeric(18,{scale})",
        existing_nullable=True,
    )


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return  # SQLite/others: schema comes from models; nothing to alter
    for t, c in _AMOUNTS:
        _alter(t, c, 2)
    for t, c in _RATES:
        _alter(t, c, 6)


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for t, c in _AMOUNTS + _RATES:
        op.alter_column(
            t, c,
            type_=sa.Float(),
            existing_type=sa.Numeric(18, 2),
            postgresql_using=f"{c}::double precision",
            existing_nullable=True,
        )
