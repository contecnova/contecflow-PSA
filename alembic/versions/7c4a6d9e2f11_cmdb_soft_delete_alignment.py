"""cmdb soft-delete alignment

Revision ID: 7c4a6d9e2f11
Revises: 1b6d9fd29b10
Create Date: 2026-05-09 12:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7c4a6d9e2f11"
down_revision: Union[str, None] = "1b6d9fd29b10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("wiki_tags", sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"))
    op.add_column("cmdb_items", sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"))
    op.add_column("cmdb_relations", sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"))
    op.add_column("kanban_columns", sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"))
    op.add_column("sprint_plans", sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"))
    op.add_column("sla_calendars", sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"))
    op.add_column("sla_calendar_holidays", sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"))


def downgrade() -> None:
    op.drop_column("sla_calendar_holidays", "is_active")
    op.drop_column("sla_calendars", "is_active")
    op.drop_column("sprint_plans", "is_active")
    op.drop_column("kanban_columns", "is_active")
    op.drop_column("cmdb_relations", "is_active")
    op.drop_column("cmdb_items", "is_active")
    op.drop_column("wiki_tags", "is_active")
