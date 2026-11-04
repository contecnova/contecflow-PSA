"""SSO: nombre visible del proveedor y claim de grupos.

Auditoria 2026-11: la lista de proveedores del login leia `sso_configs.name`,
que no existia, y devolvia vacio (ningun boton de SSO aparecia nunca); y el
mapeo de grupos a roles no tenia de donde leer los grupos.
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "122_sso_nombre_y_grupos"
down_revision: Union[str, None] = "121_motor_bpmn"
branch_labels = None
depends_on = None


def upgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("sso_configs")}
    with op.batch_alter_table("sso_configs") as batch:
        if "name" not in cols:
            batch.add_column(sa.Column("name", sa.String(120), nullable=True))
        if "groups_claim" not in cols:
            batch.add_column(sa.Column("groups_claim", sa.String(100), nullable=True, server_default="groups"))


def downgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("sso_configs")}
    with op.batch_alter_table("sso_configs") as batch:
        for c in ("groups_claim", "name"):
            if c in cols:
                batch.drop_column(c)
