"""contracts soft-delete alignment

Revision ID: e7b3a1f8c204
Revises: d4a8f2c31e09
Create Date: 2026-05-09 11:55:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e7b3a1f8c204"
down_revision: Union[str, None] = "d4a8f2c31e09"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("contracts", sa.Column("is_active", sa.Boolean(), nullable=True))
    op.execute("UPDATE contracts SET is_active = 1 WHERE is_active IS NULL")


def downgrade() -> None:
    op.drop_column("contracts", "is_active")
