"""attachment text_index column

Revision ID: e5a8b9c100e1
Revises: e5a8b9c100e0
Create Date: 2026-05-08 03:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'e5a8b9c100e1'
down_revision: Union[str, None] = 'e5a8b9c100e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('collaboration_attachments',
                  sa.Column('text_index', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('collaboration_attachments', 'text_index')
