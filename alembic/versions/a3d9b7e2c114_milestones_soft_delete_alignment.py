"""milestones soft-delete alignment

Revision ID: a3d9b7e2c114
Revises: f1c6e2a9b3d7
Create Date: 2026-05-09 12:40:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a3d9b7e2c114"
down_revision: Union[str, None] = "f1c6e2a9b3d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("project_milestones", sa.Column("is_active", sa.Boolean(), nullable=True))
    op.execute("UPDATE project_milestones SET is_active = 1 WHERE is_active IS NULL")


def downgrade() -> None:
    op.drop_column("project_milestones", "is_active")
