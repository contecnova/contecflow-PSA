"""add soft-delete is_active to rate_entries

Revision ID: 80aafca0a03b
Revises: e5f648dda455
Create Date: 2026-05-09 10:50:22.109038

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '80aafca0a03b'
down_revision: Union[str, None] = 'e5f648dda455'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('rate_entries', sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'))


def downgrade() -> None:
    op.drop_column('rate_entries', 'is_active')
