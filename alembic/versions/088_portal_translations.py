"""add portal_translations JSON column to org_brandings

Persiste las traducciones personalizadas del portal por organización (antes vivían
en un dict en memoria per-proceso, que se perdía al reiniciar y no se compartía
entre workers).

Revision ID: 088_portal_translations
Revises: 087_money_numeric_precision
Create Date: 2026-07-21
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "088_portal_translations"
down_revision: Union[str, None] = "087_money_numeric_precision"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("org_brandings", sa.Column("portal_translations", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("org_brandings", "portal_translations")
