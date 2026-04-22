"""merge_migration_heads

Revision ID: 72eb69fe644d
Revises: 02be3a225710, 030_webhook_trigger_slug_rotation
Create Date: 2026-04-22 11:56:40.457009

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '72eb69fe644d'
down_revision: Union[str, None] = ('02be3a225710', '030_webhook_trigger_slug_rotation')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
