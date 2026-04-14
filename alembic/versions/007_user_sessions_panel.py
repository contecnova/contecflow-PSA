"""Add user sessions table for active devices panel and revocation

Revision ID: 007_user_sessions_panel
Revises: 006_webauthn_passkeys
Create Date: 2026-04-07
"""
from alembic import op
import sqlalchemy as sa

revision = "007_user_sessions_panel"
down_revision = "006_webauthn_passkeys"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False, index=True),
        sa.Column("refresh_token_jti", sa.String(36), nullable=False, unique=True, index=True),
        sa.Column("ip_address", sa.String(64), nullable=True, index=True),
        sa.Column("ip_asn", sa.String(32), nullable=True),
        sa.Column("ip_org", sa.String(255), nullable=True),
        sa.Column("country_code", sa.String(8), nullable=True),
        sa.Column("region", sa.String(120), nullable=True),
        sa.Column("city", sa.String(120), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("device_name", sa.String(255), nullable=True),
        sa.Column("risk_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("risk_level", sa.String(20), nullable=False, server_default="low"),
        sa.Column("risk_reasons", sa.Text(), nullable=True),
        sa.Column("auth_method", sa.String(30), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoke_reason", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )


def downgrade():
    op.drop_table("user_sessions")
