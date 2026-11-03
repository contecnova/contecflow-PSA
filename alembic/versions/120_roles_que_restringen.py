"""Roles personalizados que se aplican: asignables y unicos por organizacion.

Auditoria 2026-11:
- `users.custom_role_id`: no habia forma de dar un rol personalizado a nadie.
- `custom_roles.name` era unico en toda la instalacion: la segunda organizacion
  que abria Ajustes > Roles intentaba sembrar «admin» otra vez y chocaba. Pasa
  a unico por (organizacion, nombre).
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "120_roles_que_restringen"
down_revision: Union[str, None] = "119_claves_de_api_que_autentican"
branch_labels = None
depends_on = None


def _unicos_de_nombre(insp) -> tuple[list[str], list[str]]:
    restr = [u["name"] for u in insp.get_unique_constraints("custom_roles")
             if u.get("column_names") == ["name"] and u.get("name")]
    # En Postgres el UNIQUE tambien sale como indice (`duplicates_constraint`):
    # se borra una sola vez, como restriccion.
    indices = [i["name"] for i in insp.get_indexes("custom_roles")
               if i.get("unique") and i.get("column_names") == ["name"]
               and not i.get("duplicates_constraint") and i["name"] not in restr]
    return restr, indices


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    restr, indices = _unicos_de_nombre(insp)
    with op.batch_alter_table("custom_roles", recreate="auto") as batch:
        for nombre in restr:
            batch.drop_constraint(nombre, type_="unique")
        for nombre in indices:
            batch.drop_index(nombre)
        batch.create_unique_constraint("uq_custom_roles_org_name", ["organization_id", "name"])

    cols = {c["name"] for c in insp.get_columns("users")}
    if "custom_role_id" not in cols:
        with op.batch_alter_table("users") as batch:
            batch.add_column(sa.Column("custom_role_id", sa.String(36), nullable=True))
            batch.create_index("ix_users_custom_role_id", ["custom_role_id"])
            batch.create_foreign_key("fk_users_custom_role_id", "custom_roles", ["custom_role_id"], ["id"],
                                     ondelete="SET NULL")


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    cols = {c["name"] for c in insp.get_columns("users")}
    if "custom_role_id" in cols:
        with op.batch_alter_table("users") as batch:
            batch.drop_constraint("fk_users_custom_role_id", type_="foreignkey")
            batch.drop_index("ix_users_custom_role_id")
            batch.drop_column("custom_role_id")
    with op.batch_alter_table("custom_roles") as batch:
        batch.drop_constraint("uq_custom_roles_org_name", type_="unique")
    # No se vuelve a poner el unico global: con roles de varias organizaciones fallaria.
