"""Add per-organization SCIM token hash (security: cross-tenant SCIM token fix)

Revision ID: 086_org_scim_token_hash
Revises: 085_settings_audit_log
Create Date: 2026-06-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "086_org_scim_token_hash"
down_revision: Union[str, None] = "085_settings_audit_log"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SHA-256 hex digest (64 chars) of the per-org SCIM bearer token. Plaintext
    # is never stored. Nullable: orgs without SCIM provisioning have no token.
    op.add_column(
        "organizations",
        sa.Column("scim_token_hash", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("organizations", "scim_token_hash")
