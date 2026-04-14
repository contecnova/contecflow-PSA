"""
Migration: Add ABAC (Attribute-Based Access Control) models

Revision ID: 009_abac_fine_grained_auth
Revises: 008_governance_scim_policy_compliance
Create Date: 2026-04-07 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision = '009_abac_fine_grained_auth'
down_revision = '008_governance_scim_policy_compliance'
branch_labels = None
depends_on = None


def upgrade():
    # Create attribute_definitions table
    op.create_table(
        'abac_attribute_definitions',
        sa.Column('id', sa.String(36), nullable=False, primary_key=True),
        sa.Column('org_id', sa.String(36), nullable=False),
        sa.Column('attribute_key', sa.String(128), nullable=False),
        sa.Column('attribute_type', sa.String(32), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('possible_values', sa.JSON, nullable=True),
        sa.Column('operators', sa.JSON, nullable=False),
        sa.Column('is_active', sa.Boolean, default=True, nullable=False),
        sa.Column('created_at', sa.DateTime, default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime, default=sa.func.now(), nullable=False),
        sa.Column('created_by', sa.String(36), nullable=True),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.Index('idx_attr_def_org_key', 'org_id', 'attribute_key'),
        sa.Index('idx_attr_def_active', 'is_active'),
    )

    # Create user_attributes table
    op.create_table(
        'user_attributes',
        sa.Column('id', sa.String(36), nullable=False, primary_key=True),
        sa.Column('user_id', sa.String(36), nullable=False),
        sa.Column('org_id', sa.String(36), nullable=False),
        sa.Column('attribute_key', sa.String(128), nullable=False),
        sa.Column('attribute_value', sa.JSON, nullable=False),
        sa.Column('expires_at', sa.DateTime, nullable=True),
        sa.Column('reason', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime, default=sa.func.now(), nullable=False),
        sa.Column('assigned_by', sa.String(36), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['assigned_by'], ['users.id'], ondelete='SET NULL'),
        sa.Index('idx_user_attr_user_org', 'user_id', 'org_id'),
        sa.Index('idx_user_attr_key', 'attribute_key'),
    )

    # Create abac_policies table
    op.create_table(
        'abac_policies',
        sa.Column('id', sa.String(36), nullable=False, primary_key=True),
        sa.Column('org_id', sa.String(36), nullable=False),
        sa.Column('policy_name', sa.String(256), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('effect', sa.String(10), default='allow', nullable=False),
        sa.Column('rules', sa.JSON, nullable=False),
        sa.Column('resource_types', sa.JSON, default=list, nullable=False),
        sa.Column('applicable_roles', sa.JSON, default=list, nullable=False),
        sa.Column('subject_users', sa.JSON, default=list, nullable=False),
        sa.Column('priority', sa.Integer, default=50, nullable=False),
        sa.Column('starts_at', sa.DateTime, nullable=True),
        sa.Column('expires_at', sa.DateTime, nullable=True),
        sa.Column('is_active', sa.Boolean, default=True, nullable=False),
        sa.Column('created_at', sa.DateTime, default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime, default=sa.func.now(), nullable=False),
        sa.Column('created_by', sa.String(36), nullable=True),
        sa.Column('last_evaluated_at', sa.DateTime, nullable=True),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.Index('idx_policy_org_active', 'org_id', 'is_active'),
        sa.Index('idx_policy_priority', 'priority'),
    )

    # Create policy_audit_log table
    op.create_table(
        'policy_audit_log',
        sa.Column('id', sa.String(36), nullable=False, primary_key=True),
        sa.Column('org_id', sa.String(36), nullable=False),
        sa.Column('user_id', sa.String(36), nullable=True),
        sa.Column('policy_id', sa.String(36), nullable=True),
        sa.Column('action', sa.String(64), nullable=False),
        sa.Column('resource_type', sa.String(128), nullable=True),
        sa.Column('resource_id', sa.String(128), nullable=True),
        sa.Column('result', sa.String(10), nullable=True),
        sa.Column('matched_policies', sa.JSON, nullable=True),
        sa.Column('evaluation_context', sa.JSON, nullable=True),
        sa.Column('detail', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['policy_id'], ['abac_policies.id'], ondelete='SET NULL'),
        sa.Index('idx_audit_org_user', 'org_id', 'user_id'),
        sa.Index('idx_audit_policy', 'policy_id'),
        sa.Index('idx_audit_action', 'action'),
        sa.Index('idx_audit_created', 'created_at'),
    )


def downgrade():
    op.drop_table('policy_audit_log')
    op.drop_table('abac_policies')
    op.drop_table('user_attributes')
    op.drop_table('abac_attribute_definitions')
