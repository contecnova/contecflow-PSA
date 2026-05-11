"""bookings soft-delete alignment

Revision ID: 9b7c1d2e4f66
Revises: 7f3b2d1c9e44
Create Date: 2026-05-09 18:05:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9b7c1d2e4f66"
down_revision: Union[str, None] = "7f3b2d1c9e44"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("resource_bookings", sa.Column("is_active", sa.Boolean(), nullable=True))
    op.execute("UPDATE resource_bookings SET is_active = 1 WHERE is_active IS NULL")


def downgrade() -> None:
    op.drop_column("resource_bookings", "is_active")
