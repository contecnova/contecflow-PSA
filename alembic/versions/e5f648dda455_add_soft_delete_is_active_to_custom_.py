"""Add soft-delete is_active to custom_fields, deliverables, and imputations

Revision ID: e5f648dda455
Revises: 115e52e0a1b2
Create Date: 2026-05-09 09:02:06.813812

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'e5f648dda455'
down_revision: Union[str, None] = '115e52e0a1b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add is_active columns for soft-delete support
    op.add_column('workflow_states', sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'))
    op.add_column('workflow_transitions', sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'))
    op.add_column('deliverables', sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'))
    op.add_column('imputations', sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'))


def downgrade() -> None:
    op.drop_column('imputations', 'is_active')
    op.drop_column('deliverables', 'is_active')
    op.drop_column('workflow_transitions', 'is_active')
    op.drop_column('workflow_states', 'is_active')
