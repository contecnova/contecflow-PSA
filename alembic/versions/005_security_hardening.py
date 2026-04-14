"""Security hardening: expand encrypted secret columns, block closed-project imputations

Revision ID: 005_security_hardening
Revises: 004_v24_features
Create Date: 2026-04-07
"""
from alembic import op
import sqlalchemy as sa

revision = '005_security_hardening'
down_revision = '004_v24_features'
branch_labels = None
depends_on = None


def upgrade():
    # ── 1. Expand users.mfa_secret from VARCHAR(64) to VARCHAR(512) ──────────
    # The column stores a Fernet-encrypted TOTP secret (v2:<salt>.<token>)
    # which is ~200 chars — VARCHAR(64) would silently truncate or error in PG.
    with op.batch_alter_table('users') as batch_op:
        batch_op.alter_column(
            'mfa_secret',
            existing_type=sa.String(64),
            type_=sa.String(512),
            nullable=True,
        )

    # ── 2. Expand mfa_configs.totp_secret from VARCHAR(64) to VARCHAR(512) ───
    with op.batch_alter_table('mfa_configs') as batch_op:
        batch_op.alter_column(
            'totp_secret',
            existing_type=sa.String(64),
            type_=sa.String(512),
            nullable=False,
        )


def downgrade():
    with op.batch_alter_table('mfa_configs') as batch_op:
        batch_op.alter_column(
            'totp_secret',
            existing_type=sa.String(512),
            type_=sa.String(64),
            nullable=False,
        )

    with op.batch_alter_table('users') as batch_op:
        batch_op.alter_column(
            'mfa_secret',
            existing_type=sa.String(512),
            type_=sa.String(64),
            nullable=True,
        )
