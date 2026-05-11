"""sprints tasks soft-delete alignment

Revision ID: 5c8e1d4a2b77
Revises: 3f7a9c2d1e55
Create Date: 2026-05-09 15:05:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "5c8e1d4a2b77"
down_revision: Union[str, None] = "3f7a9c2d1e55"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sprint_tasks", sa.Column("is_active", sa.Boolean(), nullable=True))
    op.execute("UPDATE sprint_tasks SET is_active = 1 WHERE is_active IS NULL")


def downgrade() -> None:
    op.drop_column("sprint_tasks", "is_active")
