"""changes soft-delete alignment

Revision ID: 4a1c9e8d7b33
Revises: 8d4f1b7c2a90
Create Date: 2026-05-09 16:35:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4a1c9e8d7b33"
down_revision: Union[str, None] = "8d4f1b7c2a90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("change_requests", sa.Column("is_active", sa.Boolean(), nullable=True))
    op.execute("UPDATE change_requests SET is_active = 1 WHERE is_active IS NULL")


def downgrade() -> None:
    op.drop_column("change_requests", "is_active")
