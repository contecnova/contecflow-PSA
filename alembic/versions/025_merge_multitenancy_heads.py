"""Merge multitenancy and main migration branches.

Revision ID: 025_merge_multitenancy_heads
Revises: 011_multitenancy_org_id, 024_imputation_is_invoiced
Create Date: 2026-04-16

011_multitenancy_org_id diverged from 010_security_observability
alongside 011_ai_governance_guardrails (which continued as the main
chain up to 024_imputation_is_invoiced). This merge migration re-joins
both branches into a single linear history.
"""

from alembic import op

revision = "025_merge_multitenancy_heads"
down_revision = ("011_multitenancy_org_id", "024_imputation_is_invoiced")
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No schema changes — this migration only merges the two branch heads.
    pass


def downgrade() -> None:
    pass
