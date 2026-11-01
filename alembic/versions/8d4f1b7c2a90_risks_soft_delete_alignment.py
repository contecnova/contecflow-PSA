"""risks soft-delete alignment

Revision ID: 8d4f1b7c2a90
Revises: 5c8e1d4a2b77
Create Date: 2026-05-09 16:10:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8d4f1b7c2a90"
down_revision: Union[str, None] = "5c8e1d4a2b77"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("risks", sa.Column("is_active", sa.Boolean(), nullable=True))
    op.execute("UPDATE risks SET is_active = true WHERE is_active IS NULL")


def downgrade() -> None:
    op.drop_column("risks", "is_active")
