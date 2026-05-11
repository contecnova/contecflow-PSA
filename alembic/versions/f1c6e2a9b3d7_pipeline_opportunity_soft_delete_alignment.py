"""pipeline opportunity soft-delete alignment

Revision ID: f1c6e2a9b3d7
Revises: e7b3a1f8c204
Create Date: 2026-05-09 12:20:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f1c6e2a9b3d7"
down_revision: Union[str, None] = "e7b3a1f8c204"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("opportunities", sa.Column("is_active", sa.Boolean(), nullable=True))
    op.execute("UPDATE opportunities SET is_active = 1 WHERE is_active IS NULL")


def downgrade() -> None:
    op.drop_column("opportunities", "is_active")
