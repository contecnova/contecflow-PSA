"""add_proposal_templates_and_opportunity_fields

Revision ID: b7e2c4a91f03
Revises: a3c1d8f92e05
Create Date: 2026-04-26 11:00:00.000000

Block 3 — CRM / SOW Generator:
  - Creates proposal_templates table
  - Adds proposal tracking columns to opportunities
  - Adds hourly_rate and contract_type to opportunities
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect


revision: str = 'b7e2c4a91f03'
down_revision: Union[str, None] = 'a3c1d8f92e05'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa_inspect(conn)
    existing_tables = set(inspector.get_table_names())

    # ── proposal_templates (idempotent) ────────────────────────────────────────
    if 'proposal_templates' not in existing_tables:
        op.create_table(
            'proposal_templates',
            sa.Column('id',              sa.String(36),  primary_key=True),
            sa.Column('organization_id', sa.String(36),  sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
            sa.Column('name',            sa.String(255), nullable=False),
            sa.Column('description',     sa.Text(),      nullable=True),
            sa.Column('contract_type',   sa.String(30),  nullable=True),
            sa.Column('content',         sa.Text(),      nullable=False, server_default=''),
            sa.Column('is_active',       sa.Boolean(),   nullable=False, server_default=sa.true()),
            sa.Column('created_by',      sa.String(36),  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('created_at',      sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at',      sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index('ix_proposal_templates_organization_id', 'proposal_templates', ['organization_id'])

    # ── opportunities — new columns (idempotent) ───────────────────────────────
    existing_opp_cols = {c['name'] for c in inspector.get_columns('opportunities')}
    new_cols = [
        ('hourly_rate',           sa.Float()),
        ('contract_type',         sa.String(30)),
        ('proposal_template_id',  sa.String(36)),
        ('proposal_content',      sa.Text()),
        ('proposal_generated_at', sa.DateTime(timezone=True)),
        ('proposal_sent_at',      sa.DateTime(timezone=True)),
    ]
    for col_name, col_type in new_cols:
        if col_name not in existing_opp_cols:
            op.add_column('opportunities', sa.Column(col_name, col_type, nullable=True))


def downgrade() -> None:
    op.drop_column('opportunities', 'proposal_sent_at')
    op.drop_column('opportunities', 'proposal_generated_at')
    op.drop_column('opportunities', 'proposal_content')
    op.drop_column('opportunities', 'proposal_template_id')
    op.drop_column('opportunities', 'contract_type')
    op.drop_column('opportunities', 'hourly_rate')
    op.drop_table('proposal_templates')
