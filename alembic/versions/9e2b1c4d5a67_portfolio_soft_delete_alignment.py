"""portfolio soft-delete alignment

Revision ID: 9e2b1c4d5a67
Revises: a3d9b7e2c114
Create Date: 2026-05-09 13:35:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9e2b1c4d5a67"
down_revision: Union[str, None] = "a3d9b7e2c114"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("portfolios", sa.Column("is_active", sa.Boolean(), nullable=True))
    op.add_column("portfolio_projects", sa.Column("is_active", sa.Boolean(), nullable=True))

    op.execute("UPDATE portfolios SET is_active = 1 WHERE is_active IS NULL")
    op.execute("UPDATE portfolio_projects SET is_active = 1 WHERE is_active IS NULL")


def downgrade() -> None:
    op.drop_column("portfolio_projects", "is_active")
    op.drop_column("portfolios", "is_active")
