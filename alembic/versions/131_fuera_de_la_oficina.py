"""Fuera de la oficina: delegado de aprobaciones entre dos fechas.

Revision 2026-11: mientras un aprobador esta ausente, sus avisos van tambien a
su delegado y este puede decidir los pasos que le tocarian.
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "131_fuera_de_la_oficina"
down_revision: Union[str, None] = "130_prioridad_proveedor_ia"
branch_labels = None
depends_on = None


def upgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("users")}
    with op.batch_alter_table("users") as batch:
        if "away_delegate_id" not in cols:
            batch.add_column(sa.Column("away_delegate_id", sa.String(36), nullable=True))
            batch.create_foreign_key("fk_users_away_delegate_id", "users", ["away_delegate_id"], ["id"],
                                     ondelete="SET NULL")
        if "away_from" not in cols:
            batch.add_column(sa.Column("away_from", sa.Date(), nullable=True))
        if "away_until" not in cols:
            batch.add_column(sa.Column("away_until", sa.Date(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("fk_users_away_delegate_id", type_="foreignkey")
        batch.drop_column("away_until")
        batch.drop_column("away_from")
        batch.drop_column("away_delegate_id")
