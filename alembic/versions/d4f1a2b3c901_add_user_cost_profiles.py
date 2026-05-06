"""add_user_cost_profiles

Revision ID: d4f1a2b3c901
Revises: c8e2b1d40a17
Create Date: 2026-05-06 12:00:00.000000

Creates two tables for true cost-per-hour tracking:
  country_employer_costs   — per-country presets (SS empresa %, productive hours)
  user_cost_profiles       — versioned cost profile per user (valid_from/valid_to)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = 'd4f1a2b3c901'
down_revision: Union[str, None] = 'c8e2b1d40a17'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'country_employer_costs',
        sa.Column('id',                    sa.String(36), primary_key=True),
        sa.Column('organization_id',       sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=True),
        sa.Column('country_code',          sa.String(2),  nullable=False),
        sa.Column('country_name',          sa.String(80), nullable=False),
        sa.Column('currency',              sa.String(3),  nullable=False, server_default='EUR'),
        sa.Column('employer_cost_pct',     sa.Float(),    nullable=False, server_default='0.32'),
        sa.Column('productive_hours_year', sa.Float(),    nullable=False, server_default='1700'),
        sa.Column('notes',                 sa.Text(),     nullable=True),
        sa.Column('created_at',            sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at',            sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('country_code', 'organization_id', name='ux_country_org'),
    )
    op.create_index('ix_country_employer_costs_organization_id', 'country_employer_costs', ['organization_id'])
    op.create_index('ix_country_employer_costs_country_code',    'country_employer_costs', ['country_code'])

    op.create_table(
        'user_cost_profiles',
        sa.Column('id',                    sa.String(36), primary_key=True),
        sa.Column('user_id',               sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('organization_id',       sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=True),
        sa.Column('country_code',          sa.String(2),  nullable=True),
        sa.Column('currency',              sa.String(3),  nullable=False, server_default='EUR'),
        sa.Column('gross_annual_salary',   sa.Float(),    nullable=False),
        sa.Column('employer_cost_pct',     sa.Float(),    nullable=False, server_default='0.32'),
        sa.Column('extra_annual_costs',    sa.Float(),    nullable=False, server_default='0'),
        sa.Column('productive_hours_year', sa.Float(),    nullable=False, server_default='1700'),
        sa.Column('total_annual_cost',     sa.Float(),    nullable=False),
        sa.Column('cost_per_hour',         sa.Float(),    nullable=False),
        sa.Column('valid_from',            sa.Date(),     nullable=False),
        sa.Column('valid_to',              sa.Date(),     nullable=True),
        sa.Column('notes',                 sa.Text(),     nullable=True),
        sa.Column('created_by_user_id',    sa.String(36), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at',            sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at',            sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_user_cost_profiles_user_id',         'user_cost_profiles', ['user_id'])
    op.create_index('ix_user_cost_profiles_organization_id', 'user_cost_profiles', ['organization_id'])
    op.create_index('ix_user_cost_profiles_country_code',    'user_cost_profiles', ['country_code'])
    op.create_index('ix_user_cost_profiles_valid_from',      'user_cost_profiles', ['valid_from'])
    op.create_index('ix_user_cost_profiles_valid_to',        'user_cost_profiles', ['valid_to'])


def downgrade() -> None:
    op.drop_index('ix_user_cost_profiles_valid_to',        table_name='user_cost_profiles')
    op.drop_index('ix_user_cost_profiles_valid_from',      table_name='user_cost_profiles')
    op.drop_index('ix_user_cost_profiles_country_code',    table_name='user_cost_profiles')
    op.drop_index('ix_user_cost_profiles_organization_id', table_name='user_cost_profiles')
    op.drop_index('ix_user_cost_profiles_user_id',         table_name='user_cost_profiles')
    op.drop_table('user_cost_profiles')
    op.drop_index('ix_country_employer_costs_country_code',    table_name='country_employer_costs')
    op.drop_index('ix_country_employer_costs_organization_id', table_name='country_employer_costs')
    op.drop_table('country_employer_costs')
