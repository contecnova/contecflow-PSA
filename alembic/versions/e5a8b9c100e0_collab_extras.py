"""collaboration extras: saved queries + push subscriptions + integration tokens

Revision ID: e5a8b9c100e0
Revises: e5a8b9c100df
Create Date: 2026-05-08 02:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'e5a8b9c100e0'
down_revision: Union[str, None] = 'e5a8b9c100df'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'collaboration_saved_searches',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('name', sa.String(120), nullable=False),
        sa.Column('query', sa.String(500), nullable=False),
        sa.Column('parsed', sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column('is_pinned', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('use_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        'collaboration_push_subscriptions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=True, index=True),
        sa.Column('client_user_id', sa.String(36), sa.ForeignKey('client_users.id', ondelete='CASCADE'), nullable=True, index=True),
        sa.Column('endpoint', sa.String(800), nullable=False),
        sa.Column('p256dh_key', sa.String(255), nullable=False),
        sa.Column('auth_key', sa.String(255), nullable=False),
        sa.Column('user_agent', sa.String(255), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('endpoint', name='uq_push_endpoint'),
    )

    # Persist OAuth refresh tokens per integration (encrypted in prod via secret_ref)
    op.add_column('collaboration_integrations',
                  sa.Column('access_token_enc', sa.Text(), nullable=True))
    op.add_column('collaboration_integrations',
                  sa.Column('refresh_token_enc', sa.Text(), nullable=True))
    op.add_column('collaboration_integrations',
                  sa.Column('token_expires_at', sa.DateTime(timezone=True), nullable=True))

    # Attachment thumbnail status (for async preview generation)
    op.add_column('collaboration_attachments',
                  sa.Column('preview_status', sa.String(40), nullable=False, server_default='none'))


def downgrade() -> None:
    op.drop_column('collaboration_attachments', 'preview_status')
    op.drop_column('collaboration_integrations', 'token_expires_at')
    op.drop_column('collaboration_integrations', 'refresh_token_enc')
    op.drop_column('collaboration_integrations', 'access_token_enc')
    op.drop_table('collaboration_push_subscriptions')
    op.drop_table('collaboration_saved_searches')
