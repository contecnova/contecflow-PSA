"""add_bpmn_process_registry

Revision ID: c8e2b1d40a17
Revises: 061_unify_roles
Create Date: 2026-05-06 09:00:00.000000

Creates the BPMN Process Registry tables that back the in-app BPMN editor:
  bpmn_processes         — one row per process (metadata + latest version pointer)
  bpmn_process_versions  — versioned BPMN 2.0 XML payloads per process
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = 'c8e2b1d40a17'
down_revision: Union[str, None] = '061_unify_roles'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'bpmn_processes',
        sa.Column('id',                 sa.String(36),  primary_key=True),
        sa.Column('organization_id',    sa.String(36),  sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=True),
        sa.Column('key',                sa.String(120), nullable=False),
        sa.Column('name',                sa.String(255), nullable=False),
        sa.Column('description',         sa.Text(),      nullable=True),
        sa.Column('category',            sa.String(80),  nullable=False),
        sa.Column('icon',                sa.String(40),  nullable=True),
        sa.Column('source_kind',         sa.String(40),  nullable=True),
        sa.Column('source_ref',          sa.String(255), nullable=True),
        sa.Column('latest_version',      sa.Integer(),   nullable=False, server_default='1'),
        sa.Column('status',              sa.String(20),  nullable=False, server_default='draft'),
        sa.Column('is_seeded',           sa.Boolean(),   nullable=False, server_default=sa.false()),
        sa.Column('is_active',           sa.Boolean(),   nullable=False, server_default=sa.true()),
        sa.Column('created_by_user_id',  sa.String(36),  sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at',          sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at',          sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_bpmn_processes_organization_id', 'bpmn_processes', ['organization_id'])
    op.create_index('ix_bpmn_processes_key',             'bpmn_processes', ['key'])
    op.create_index('ix_bpmn_processes_category',        'bpmn_processes', ['category'])

    op.create_table(
        'bpmn_process_versions',
        sa.Column('id',                  sa.String(36), primary_key=True),
        sa.Column('process_id',          sa.String(36), sa.ForeignKey('bpmn_processes.id', ondelete='CASCADE'), nullable=False),
        sa.Column('version',             sa.Integer(),  nullable=False),
        sa.Column('bpmn_xml',            sa.Text(),     nullable=False),
        sa.Column('notes',               sa.String(500), nullable=True),
        sa.Column('is_published',        sa.Boolean(),  nullable=False, server_default=sa.false()),
        sa.Column('published_at',        sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by_user_id',  sa.String(36), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at',          sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_bpmn_process_versions_process_id', 'bpmn_process_versions', ['process_id'])


def downgrade() -> None:
    op.drop_index('ix_bpmn_process_versions_process_id', table_name='bpmn_process_versions')
    op.drop_table('bpmn_process_versions')
    op.drop_index('ix_bpmn_processes_category', table_name='bpmn_processes')
    op.drop_index('ix_bpmn_processes_key', table_name='bpmn_processes')
    op.drop_index('ix_bpmn_processes_organization_id', table_name='bpmn_processes')
    op.drop_table('bpmn_processes')
