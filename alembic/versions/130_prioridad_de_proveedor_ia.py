"""Proveedores de IA: orden de respaldo.

Revision 2026-11: si el proveedor elegido falla se prueban los demas por
`priority` (de menor a mayor); antes, en el orden en que salian de la base.
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "130_prioridad_proveedor_ia"
down_revision: Union[str, None] = "129_aprobaciones_delegacion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "priority" not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("ai_providers")}:
        with op.batch_alter_table("ai_providers") as batch:
            batch.add_column(sa.Column("priority", sa.Integer(), nullable=False, server_default="100"))


def downgrade() -> None:
    with op.batch_alter_table("ai_providers") as batch:
        batch.drop_column("priority")
