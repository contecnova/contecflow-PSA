"""projects members soft-delete alignment

Revision ID: 6a4d2e1f9b88
Revises: 9e2b1c4d5a67
Create Date: 2026-05-09 14:05:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "6a4d2e1f9b88"
down_revision: Union[str, None] = "9e2b1c4d5a67"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("project_members", sa.Column("is_active", sa.Boolean(), nullable=True))
    op.execute("UPDATE project_members SET is_active = 1 WHERE is_active IS NULL")


def downgrade() -> None:
    op.drop_column("project_members", "is_active")
