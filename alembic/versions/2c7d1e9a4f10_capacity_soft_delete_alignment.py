"""capacity soft-delete alignment

Revision ID: 2c7d1e9a4f10
Revises: 4a1c9e8d7b33
Create Date: 2026-05-09 16:55:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "2c7d1e9a4f10"
down_revision: Union[str, None] = "4a1c9e8d7b33"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("capacity_plans", sa.Column("is_active", sa.Boolean(), nullable=True))
    op.execute("UPDATE capacity_plans SET is_active = true WHERE is_active IS NULL")


def downgrade() -> None:
    op.drop_column("capacity_plans", "is_active")
