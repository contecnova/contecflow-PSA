"""Baja definitiva de una empresa: cuarentena antes de borrar sus datos.

Revision multitenant 2026-11 (como contecpos): pedir la baja suspende la
empresa y fija `deletion_purge_after`; hasta entonces se puede deshacer y
exportar. Ver app/services/baja_de_empresa_service.py.
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "128_baja_de_empresa"
down_revision: Union[str, None] = "127_motivo_de_suspension"
branch_labels = None
depends_on = None

_COLUMNAS = (
    ("deletion_requested_at", sa.DateTime(timezone=True)),
    ("deletion_purge_after", sa.DateTime(timezone=True)),
    ("deletion_requested_by", sa.String(36)),
)


def upgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("organizations")}
    with op.batch_alter_table("organizations") as batch:
        for nombre, tipo in _COLUMNAS:
            if nombre not in cols:
                batch.add_column(sa.Column(nombre, tipo, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("organizations") as batch:
        for nombre, _ in _COLUMNAS:
            batch.drop_column(nombre)
