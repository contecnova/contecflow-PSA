"""alm soft-delete alignment

Revision ID: b2e8c4a91d44
Revises: 7c4a6d9e2f11
Create Date: 2026-05-09 13:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b2e8c4a91d44"
down_revision: Union[str, None] = "7c4a6d9e2f11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("alm_contracts", sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"))
    op.add_column("alm_licenses", sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"))
    op.add_column("alm_assets", sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"))
    op.add_column("alm_software_installs", sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"))


def downgrade() -> None:
    op.drop_column("alm_software_installs", "is_active")
    op.drop_column("alm_assets", "is_active")
    op.drop_column("alm_licenses", "is_active")
    op.drop_column("alm_contracts", "is_active")
