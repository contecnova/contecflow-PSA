"""epics soft-delete alignment

Revision ID: c9f1e7a45d22
Revises: b2e8c4a91d44
Create Date: 2026-05-09 10:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c9f1e7a45d22"
down_revision: Union[str, None] = "b2e8c4a91d44"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("wiki_spaces", sa.Column("is_active", sa.Boolean(), nullable=True))
    op.add_column("wiki_pages", sa.Column("is_active", sa.Boolean(), nullable=True))
    op.add_column("epics", sa.Column("is_active", sa.Boolean(), nullable=True))
    op.add_column("epic_tasks", sa.Column("is_active", sa.Boolean(), nullable=True))
    op.add_column("epic_dependencies", sa.Column("is_active", sa.Boolean(), nullable=True))
    op.add_column("saved_filters", sa.Column("is_active", sa.Boolean(), nullable=True))
    op.add_column("threaded_comments", sa.Column("is_active", sa.Boolean(), nullable=True))

    op.execute("UPDATE wiki_spaces SET is_active = true WHERE is_active IS NULL")
    op.execute("UPDATE wiki_pages SET is_active = true WHERE is_active IS NULL")
    op.execute("UPDATE epics SET is_active = true WHERE is_active IS NULL")
    op.execute("UPDATE epic_tasks SET is_active = true WHERE is_active IS NULL")
    op.execute("UPDATE epic_dependencies SET is_active = true WHERE is_active IS NULL")
    op.execute("UPDATE saved_filters SET is_active = true WHERE is_active IS NULL")
    op.execute("UPDATE threaded_comments SET is_active = true WHERE is_active IS NULL")


def downgrade() -> None:
    op.drop_column("threaded_comments", "is_active")
    op.drop_column("saved_filters", "is_active")
    op.drop_column("epic_dependencies", "is_active")
    op.drop_column("epic_tasks", "is_active")
    op.drop_column("epics", "is_active")
    op.drop_column("wiki_pages", "is_active")
    op.drop_column("wiki_spaces", "is_active")
