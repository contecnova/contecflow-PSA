"""Create document management tables

Revision ID: 003_document_management
Revises: 002_...
Create Date: 2026-04-03

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '003_document_management'
down_revision = '002_incremental'  # Change to actual previous revision
branch_labels = None
depends_on = None


def upgrade():
    """Create new tables for document management and enhanced features."""

    # Document table
    op.create_table(
        'documents',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('title', sa.String(255), nullable=False, index=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category', sa.String(50), nullable=False, index=True),
        sa.Column('project_id', sa.String(36), nullable=True, index=True),
        sa.Column('client_id', sa.String(36), nullable=True, index=True),
        sa.Column('milestone_id', sa.String(36), nullable=True, index=True),
        sa.Column('task_id', sa.String(36), nullable=True, index=True),
        sa.Column('ticket_id', sa.String(36), nullable=True, index=True),
        sa.Column('requires_approval', sa.Boolean(), default=False),
        sa.Column('approval_status', sa.String(20), default='pending'),
        sa.Column('approved_by', sa.String(36), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_archived', sa.Boolean(), default=False, index=True),
        sa.Column('created_by', sa.String(36), nullable=False, index=True),
        sa.Column('updated_by', sa.String(36), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['milestone_id'], ['project_milestones.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['ticket_id'], ['sd_tickets.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['approved_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )

    # DocumentVersion table
    op.create_table(
        'document_versions',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('document_id', sa.String(36), nullable=False, index=True),
        sa.Column('version_num', sa.Integer(), nullable=False),
        sa.Column('file_key', sa.String(500), nullable=False),
        sa.Column('file_name', sa.String(255), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=True),
        sa.Column('file_mime_type', sa.String(100), nullable=True),
        sa.Column('s3_url', sa.String(1000), nullable=True),
        sa.Column('s3_url_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('change_note', sa.String(500), nullable=True),
        sa.Column('created_by', sa.String(36), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )

    # DocumentPermission table
    op.create_table(
        'document_permissions',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('document_id', sa.String(36), nullable=False, index=True),
        sa.Column('user_id', sa.String(36), nullable=False, index=True),
        sa.Column('access_level', sa.String(20), nullable=False),
        sa.Column('granted_by', sa.String(36), nullable=True),
        sa.Column('granted_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['granted_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )

    # DocumentTag table
    op.create_table(
        'document_tags',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('document_id', sa.String(36), nullable=False, index=True),
        sa.Column('tag_name', sa.String(100), nullable=False, index=True),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Timer Sessions
    op.create_table(
        'timer_sessions',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('user_id', sa.String(36), nullable=False, unique=True, index=True),
        sa.Column('task_id', sa.String(36), nullable=True),
        sa.Column('project_id', sa.String(36), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('paused_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('paused_duration_secs', sa.Integer(), default=0),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('imputation_id', sa.String(36), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['imputation_id'], ['imputations.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )

    # Imputation Alerts
    op.create_table(
        'imputation_alerts',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('user_id', sa.String(36), nullable=False, index=True),
        sa.Column('alert_date', sa.Date(), nullable=False, index=True),
        sa.Column('alert_type', sa.String(50), default='missing_hours'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('dismissed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Imputation Snapshots
    op.create_table(
        'imputation_snapshots',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('user_id', sa.String(36), nullable=False, index=True),
        sa.Column('snapshot_date', sa.Date(), nullable=False, index=True),
        sa.Column('total_hours', sa.Float(), default=0.0),
        sa.Column('billable_hours', sa.Float(), default=0.0),
        sa.Column('approved_hours', sa.Float(), default=0.0),
        sa.Column('is_complete', sa.Boolean(), default=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Resource Alerts
    op.create_table(
        'resource_alerts',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('user_id', sa.String(36), nullable=False, index=True),
        sa.Column('alert_type', sa.String(50), nullable=False, index=True),
        sa.Column('context', sa.Text(), nullable=True),
        sa.Column('severity', sa.String(20), default='warning'),
        sa.Column('triggered_at', sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
        sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('acknowledged_by', sa.String(36), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['acknowledged_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )

    # Resource Utilization Snapshots
    op.create_table(
        'resource_utilization_snapshots',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('user_id', sa.String(36), nullable=False, index=True),
        sa.Column('week_iso', sa.String(10), nullable=False, index=True),
        sa.Column('planned_hours', sa.Float(), default=0.0),
        sa.Column('actual_hours', sa.Float(), default=0.0),
        sa.Column('billable_hours', sa.Float(), default=0.0),
        sa.Column('utilization_pct', sa.Float(), nullable=True),
        sa.Column('billable_pct', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Add column to organizations table
    op.add_column('organizations', sa.Column('imputation_lockout_days', sa.Integer(), default=14))


def downgrade():
    """Drop all new tables."""
    op.drop_table('resource_utilization_snapshots')
    op.drop_table('resource_alerts')
    op.drop_table('imputation_snapshots')
    op.drop_table('imputation_alerts')
    op.drop_table('timer_sessions')
    op.drop_table('document_tags')
    op.drop_table('document_permissions')
    op.drop_table('document_versions')
    op.drop_table('documents')
    op.drop_column('organizations', 'imputation_lockout_days')
