"""Add organization_id to ai_providers and rate_tables for tenant isolation.

Revision ID: 020_tenant_scope_ai_providers_and_rate_tables
Revises: 019
Create Date: 2026-04-12
"""
from alembic import op
import sqlalchemy as sa


revision = '020_tenant_scope_ai_providers_and_rate_tables'
down_revision = '019'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Add nullable tenant columns first for safe backfill.
    op.add_column('ai_providers', sa.Column('organization_id', sa.String(length=36), nullable=True))
    op.add_column('rate_tables', sa.Column('organization_id', sa.String(length=36), nullable=True))

    op.create_foreign_key(
        'fk_ai_providers_organization_id',
        'ai_providers',
        'organizations',
        ['organization_id'],
        ['id'],
        ondelete='CASCADE',
    )
    op.create_foreign_key(
        'fk_rate_tables_organization_id',
        'rate_tables',
        'organizations',
        ['organization_id'],
        ['id'],
        ondelete='CASCADE',
    )

    op.create_index('ix_ai_providers_organization_id', 'ai_providers', ['organization_id'])
    op.create_index('ix_rate_tables_organization_id', 'rate_tables', ['organization_id'])

    conn = op.get_bind()

    # 2) Backfill AI providers from creator user org where available.
    conn.execute(sa.text(
        """
        UPDATE ai_providers ap
           SET organization_id = u.organization_id
          FROM users u
         WHERE ap.created_by = u.id
           AND ap.organization_id IS NULL
           AND u.organization_id IS NOT NULL
        """
    ))

    # 3) Backfill rate tables from existing relations (project/client overrides), then creator fallback.
    conn.execute(sa.text(
        """
        UPDATE rate_tables rt
           SET organization_id = p.organization_id
          FROM rate_overrides ro
          JOIN projects p ON p.id = ro.project_id
         WHERE ro.table_id = rt.id
           AND rt.organization_id IS NULL
           AND p.organization_id IS NOT NULL
        """
    ))
    conn.execute(sa.text(
        """
        UPDATE rate_tables rt
           SET organization_id = p.organization_id
          FROM rate_overrides ro
          JOIN clients c ON c.id = ro.client_id
          JOIN projects p ON p.client_id = c.id
         WHERE ro.table_id = rt.id
           AND rt.organization_id IS NULL
           AND p.organization_id IS NOT NULL
        """
    ))

    # 4) If still NULL, keep nullable for compatibility; endpoint logic will exclude NULL for non-superadmin.


def downgrade() -> None:
    op.drop_index('ix_rate_tables_organization_id', table_name='rate_tables')
    op.drop_index('ix_ai_providers_organization_id', table_name='ai_providers')

    op.drop_constraint('fk_rate_tables_organization_id', 'rate_tables', type_='foreignkey')
    op.drop_constraint('fk_ai_providers_organization_id', 'ai_providers', type_='foreignkey')

    op.drop_column('rate_tables', 'organization_id')
    op.drop_column('ai_providers', 'organization_id')
