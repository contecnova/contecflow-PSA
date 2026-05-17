"""Per-organization encrypted integration credentials.

Backs the IntegrationCredential model — one row per (org, provider, key) so
that admin-editable per-tenant settings (SMTP host, AWS keys, Stripe webhook
secret, etc.) can live in the DB with encryption at rest instead of in env.

Revision ID: 084_integration_credentials
Revises: 083_pg_trgm_search_indexes
Create Date: 2026-05-16
"""

from alembic import op
import sqlalchemy as sa


revision = "084_integration_credentials"
down_revision = "083_pg_trgm_search_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "integration_credentials",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("key", sa.String(80), nullable=False),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("value_encrypted", sa.Text(), nullable=True),
        sa.Column(
            "is_secret",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("updated_by", sa.String(36), nullable=True),
        sa.UniqueConstraint(
            "organization_id", "provider", "key", name="uq_integration_credential"
        ),
    )
    op.create_index(
        "ix_integration_credentials_organization_id",
        "integration_credentials",
        ["organization_id"],
    )
    op.create_index(
        "ix_integration_credential_provider",
        "integration_credentials",
        ["provider"],
    )


def downgrade() -> None:
    op.drop_index("ix_integration_credential_provider", table_name="integration_credentials")
    op.drop_index(
        "ix_integration_credentials_organization_id",
        table_name="integration_credentials",
    )
    op.drop_table("integration_credentials")
