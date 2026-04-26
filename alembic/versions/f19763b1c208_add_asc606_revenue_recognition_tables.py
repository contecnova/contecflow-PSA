"""add_asc606_revenue_recognition_tables

Revision ID: f19763b1c208
Revises: 72eb69fe644d
Create Date: 2026-04-25 18:30:00.000000

Creates four new tables for ASC 606 / IFRS 15 revenue recognition:
  rev_contracts      — contract-level config per project
  rev_obligations    — performance obligations within a contract
  rev_period_closes  — immutable monthly accounting closes
  rev_entries        — immutable accounting recognition entries
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = 'f19763b1c208'
down_revision: Union[str, None] = '72eb69fe644d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── rev_contracts ──────────────────────────────────────────────────────────
    op.create_table(
        'rev_contracts',
        sa.Column('id',              sa.String(36),  primary_key=True),
        sa.Column('organization_id', sa.String(36),  sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('project_id',      sa.String(36),  sa.ForeignKey('projects.id',      ondelete='CASCADE'), nullable=False),
        sa.Column('client_id',       sa.String(36),  sa.ForeignKey('clients.id',        ondelete='SET NULL'), nullable=True),
        sa.Column('name',            sa.String(255), nullable=False),
        sa.Column('contract_value',  sa.Float(),     nullable=False, server_default='0'),
        sa.Column('currency',        sa.String(8),   nullable=False, server_default='EUR'),
        sa.Column('method',          sa.String(30),  nullable=False, server_default='over_time'),
        sa.Column('start_date',      sa.Date(),      nullable=True),
        sa.Column('end_date',        sa.Date(),      nullable=True),
        sa.Column('duration_months', sa.Integer(),   nullable=True),
        sa.Column('is_active',       sa.Boolean(),   nullable=False, server_default=sa.true()),
        sa.Column('notes',           sa.Text(),      nullable=True),
        sa.Column('created_at',      sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at',      sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_rev_contracts_organization_id', 'rev_contracts', ['organization_id'])
    op.create_index('ix_rev_contracts_project_id',      'rev_contracts', ['project_id'])

    # ── rev_obligations ────────────────────────────────────────────────────────
    op.create_table(
        'rev_obligations',
        sa.Column('id',               sa.String(36),  primary_key=True),
        sa.Column('organization_id',  sa.String(36),  sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('contract_id',      sa.String(36),  sa.ForeignKey('rev_contracts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('milestone_id',     sa.String(36),  sa.ForeignKey('milestones.id',    ondelete='SET NULL'), nullable=True),
        sa.Column('name',             sa.String(255), nullable=False),
        sa.Column('allocated_pct',    sa.Float(),     nullable=False, server_default='100'),
        sa.Column('allocated_amount', sa.Float(),     nullable=False, server_default='0'),
        sa.Column('is_satisfied',     sa.Boolean(),   nullable=False, server_default=sa.false()),
        sa.Column('satisfied_date',   sa.Date(),      nullable=True),
        sa.Column('created_at',       sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_rev_obligations_organization_id', 'rev_obligations', ['organization_id'])
    op.create_index('ix_rev_obligations_contract_id',     'rev_obligations', ['contract_id'])

    # ── rev_period_closes ──────────────────────────────────────────────────────
    op.create_table(
        'rev_period_closes',
        sa.Column('id',              sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('period_year',     sa.Integer(),  nullable=False),
        sa.Column('period_month',    sa.Integer(),  nullable=False),
        sa.Column('closed_by',       sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('closed_at',       sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('notes',           sa.Text(),     nullable=True),
        sa.UniqueConstraint('organization_id', 'period_year', 'period_month', name='uq_period_close'),
    )
    op.create_index('ix_rev_period_closes_organization_id', 'rev_period_closes', ['organization_id'])

    # ── rev_entries ────────────────────────────────────────────────────────────
    op.create_table(
        'rev_entries',
        sa.Column('id',                sa.String(36), primary_key=True),
        sa.Column('organization_id',   sa.String(36), sa.ForeignKey('organizations.id',    ondelete='CASCADE'),  nullable=False),
        sa.Column('rev_contract_id',   sa.String(36), sa.ForeignKey('rev_contracts.id',    ondelete='RESTRICT'), nullable=False),
        sa.Column('period_close_id',   sa.String(36), sa.ForeignKey('rev_period_closes.id', ondelete='SET NULL'), nullable=True),
        sa.Column('milestone_id',      sa.String(36), sa.ForeignKey('milestones.id',        ondelete='SET NULL'), nullable=True),
        sa.Column('timesheet_id',      sa.String(36), nullable=True),
        sa.Column('entry_type',        sa.String(20), nullable=False, server_default='recognized'),
        sa.Column('amount',            sa.Float(),    nullable=False, server_default='0'),
        sa.Column('currency',          sa.String(8),  nullable=False, server_default='EUR'),
        sa.Column('period_year',       sa.Integer(),  nullable=False),
        sa.Column('period_month',      sa.Integer(),  nullable=False),
        sa.Column('reverses_entry_id', sa.String(36), sa.ForeignKey('rev_entries.id', ondelete='SET NULL'), nullable=True),
        sa.Column('description',       sa.Text(),     nullable=True),
        sa.Column('created_by',        sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at',        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_rev_entries_organization_id',  'rev_entries', ['organization_id'])
    op.create_index('ix_rev_entries_rev_contract_id',  'rev_entries', ['rev_contract_id'])


def downgrade() -> None:
    op.drop_table('rev_entries')
    op.drop_table('rev_period_closes')
    op.drop_table('rev_obligations')
    op.drop_table('rev_contracts')
