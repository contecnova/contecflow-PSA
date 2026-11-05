"""Motivo de la suspension de una empresa.

Revision multitenant 2026-11: suspender una empresa (corta en el acto sus
sesiones) pide un motivo, que la pantalla de empresas ensena; reactivar lo borra.
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "127_motivo_de_suspension"
down_revision: Union[str, None] = "126_dominio_de_la_organizacion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("organizations")}
    if "suspension_reason" not in cols:
        with op.batch_alter_table("organizations") as batch:
            batch.add_column(sa.Column("suspension_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("organizations") as batch:
        batch.drop_column("suspension_reason")
