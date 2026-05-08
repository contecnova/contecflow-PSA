"""audit chain prev_event_id

Revision ID: e5a8b9c100df
Revises: e5a8b9c100de
Create Date: 2026-05-08 00:30:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'e5a8b9c100df'
down_revision: Union[str, None] = 'e5a8b9c100de'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('collaboration_audit_events',
                  sa.Column('prev_event_id', sa.String(36), nullable=True))


def downgrade() -> None:
    op.drop_column('collaboration_audit_events', 'prev_event_id')
