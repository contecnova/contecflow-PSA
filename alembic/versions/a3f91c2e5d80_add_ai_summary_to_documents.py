"""add ai_summary to documents

Revision ID: a3f91c2e5d80
Revises: c4e5f2a83d17
Create Date: 2026-05-04 00:00:00.000000
"""
from typing import Union
from alembic import op
import sqlalchemy as sa

revision: str = 'a3f91c2e5d80'
down_revision: Union[str, None] = 'c4e5f2a83d17'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('documents', sa.Column('ai_summary', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('documents', 'ai_summary')
