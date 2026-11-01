"""absences soft-delete alignment

Revision ID: 7f3b2d1c9e44
Revises: 2c7d1e9a4f10
Create Date: 2026-05-09 17:15:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7f3b2d1c9e44"
down_revision: Union[str, None] = "2c7d1e9a4f10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("absences", sa.Column("is_active", sa.Boolean(), nullable=True))
    op.execute("UPDATE absences SET is_active = true WHERE is_active IS NULL")


def downgrade() -> None:
    op.drop_column("absences", "is_active")
