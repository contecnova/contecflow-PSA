"""018 - Drop users.refresh_token_jti (superseded by UserSession.refresh_token_jti)

Revision ID: 018_drop_user_refresh_token_jti
Revises: 017_mfa_sso_hardening
Create Date: 2026-04-13 00:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "018_drop_user_refresh_token_jti"
down_revision = "017_mfa_sso_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The per-user global JTI column has been replaced by the per-session JTI
    # tracked in user_sessions.refresh_token_jti (migration 007_user_sessions).
    # Keeping both created ambiguous fallback logic in auth.py; removed in code;
    # now dropping from the DB schema as well.
    op.drop_column("users", "refresh_token_jti")


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column("refresh_token_jti", sa.String(length=36), nullable=True),
    )
