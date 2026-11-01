"""clients link soft-delete alignment

Revision ID: d4a8f2c31e09
Revises: c9f1e7a45d22
Create Date: 2026-05-09 11:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4a8f2c31e09"
down_revision: Union[str, None] = "c9f1e7a45d22"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("client_license_links", sa.Column("is_active", sa.Boolean(), nullable=True))
    op.add_column("client_contract_links", sa.Column("is_active", sa.Boolean(), nullable=True))

    op.execute("UPDATE client_license_links SET is_active = true WHERE is_active IS NULL")
    op.execute("UPDATE client_contract_links SET is_active = true WHERE is_active IS NULL")


def downgrade() -> None:
    op.drop_column("client_contract_links", "is_active")
    op.drop_column("client_license_links", "is_active")
