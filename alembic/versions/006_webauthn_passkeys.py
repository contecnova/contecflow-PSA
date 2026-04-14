"""Add WebAuthn/FIDO2 passkey credentials table

Revision ID: 006_webauthn_passkeys
Revises: 005_security_hardening
Create Date: 2026-04-07
"""
from alembic import op
import sqlalchemy as sa

revision = '006_webauthn_passkeys'
down_revision = '005_security_hardening'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'webauthn_credentials',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), nullable=False, index=True),
        sa.Column('credential_id', sa.String(255), nullable=False, unique=True, index=True),
        sa.Column('public_key', sa.Text(), nullable=False),
        sa.Column('sign_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('transports', sa.Text(), nullable=True),
        sa.Column('name', sa.String(100), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )


def downgrade():
    op.drop_table('webauthn_credentials')
