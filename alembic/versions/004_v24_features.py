"""v24 features: timezone per user, recurring billing, public forms, oauth apps

Revision ID: 004_v24_features
Revises: 003_document_management
Create Date: 2026-04-07
"""
from alembic import op
import sqlalchemy as sa

revision = '004_v24_features'
down_revision = '003_document_management'
branch_labels = None
depends_on = None


def upgrade():
    # ── 1. Timezone per user ──────────────────────────────────────────────────
    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('timezone', sa.String(50), nullable=True))

    # ── 2. Recurring billing on projects ─────────────────────────────────────
    with op.batch_alter_table('projects') as batch_op:
        batch_op.add_column(sa.Column('retainer_amount', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('retainer_day', sa.Integer(), nullable=True))

    # ── 3. Public intake forms ────────────────────────────────────────────────
    op.create_table(
        'public_forms',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('form_type', sa.String(20), nullable=False, index=True),  # ticket | task
        sa.Column('token', sa.String(64), nullable=False, unique=True, index=True),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('target_project_id', sa.String(36), nullable=True),
        sa.Column('target_group_id', sa.String(36), nullable=True),
        sa.Column('default_priority', sa.String(20), default='medium'),
        sa.Column('default_category', sa.String(100), nullable=True),
        sa.Column('fields_config', sa.Text(), default='[]'),  # JSON
        sa.Column('success_message', sa.String(500), nullable=True),
        sa.Column('notify_emails', sa.Text(), default='[]'),   # JSON email list
        sa.Column('submission_count', sa.Integer(), default=0),
        sa.Column('created_by', sa.String(36), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['target_project_id'], ['projects.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
    )

    op.create_table(
        'public_form_submissions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('form_id', sa.String(36), nullable=False, index=True),
        sa.Column('submitter_name', sa.String(255), nullable=True),
        sa.Column('submitter_email', sa.String(255), nullable=True),
        sa.Column('subject', sa.String(500), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('priority', sa.String(20), default='medium'),
        sa.Column('category', sa.String(100), nullable=True),
        sa.Column('extra_fields', sa.Text(), default='{}'),  # JSON
        sa.Column('created_entity_id', sa.String(36), nullable=True),  # ticket/task id created
        sa.Column('created_entity_type', sa.String(20), nullable=True),  # ticket | task
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('submitted_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['form_id'], ['public_forms.id'], ondelete='CASCADE'),
    )

    # ── 4. OAuth apps (developer portal) ─────────────────────────────────────
    op.create_table(
        'oauth_apps',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('homepage_url', sa.String(500), nullable=True),
        sa.Column('client_id', sa.String(64), nullable=False, unique=True, index=True),
        sa.Column('client_secret_hash', sa.String(255), nullable=False),
        sa.Column('redirect_uris', sa.Text(), nullable=False, default='[]'),  # JSON
        sa.Column('scopes', sa.Text(), nullable=False, default='["read"]'),   # JSON
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('is_first_party', sa.Boolean(), default=False),
        sa.Column('owner_id', sa.String(36), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='SET NULL'),
    )

    op.create_table(
        'oauth_tokens',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('app_id', sa.String(36), nullable=False, index=True),
        sa.Column('user_id', sa.String(36), nullable=False, index=True),
        sa.Column('access_token_hash', sa.String(255), nullable=False),
        sa.Column('refresh_token_hash', sa.String(255), nullable=True),
        sa.Column('scopes', sa.Text(), nullable=False, default='["read"]'),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked', sa.Boolean(), default=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['app_id'], ['oauth_apps.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )


def downgrade():
    op.drop_table('oauth_tokens')
    op.drop_table('oauth_apps')
    op.drop_table('public_form_submissions')
    op.drop_table('public_forms')
    with op.batch_alter_table('projects') as batch_op:
        batch_op.drop_column('retainer_day')
        batch_op.drop_column('retainer_amount')
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('timezone')
