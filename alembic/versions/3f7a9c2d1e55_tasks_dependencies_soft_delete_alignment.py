"""tasks dependencies soft-delete alignment

Revision ID: 3f7a9c2d1e55
Revises: 6a4d2e1f9b88
Create Date: 2026-05-09 14:35:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "3f7a9c2d1e55"
down_revision: Union[str, None] = "6a4d2e1f9b88"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("task_dependencies", sa.Column("is_active", sa.Boolean(), nullable=True))
    op.execute("UPDATE task_dependencies SET is_active = true WHERE is_active IS NULL")


def downgrade() -> None:
    op.drop_column("task_dependencies", "is_active")
