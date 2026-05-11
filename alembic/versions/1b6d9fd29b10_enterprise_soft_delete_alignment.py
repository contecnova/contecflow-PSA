"""enterprise soft-delete alignment

Revision ID: 1b6d9fd29b10
Revises: 80aafca0a03b
Create Date: 2026-05-09 12:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "1b6d9fd29b10"
down_revision: Union[str, None] = "80aafca0a03b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("project_permissions", sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"))
    op.add_column("sso_configs", sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="0"))
    op.add_column("notifications", sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"))
    op.add_column("subcontractor_rates", sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"))
    op.add_column("subcontractor_worker_skills", sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"))
    op.add_column("subcontractor_timelogs", sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"))


def downgrade() -> None:
    op.drop_column("subcontractor_timelogs", "is_active")
    op.drop_column("subcontractor_worker_skills", "is_active")
    op.drop_column("subcontractor_rates", "is_active")
    op.drop_column("notifications", "is_active")
    op.drop_column("sso_configs", "is_deleted")
    op.drop_column("project_permissions", "is_active")
