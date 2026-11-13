"""Perfil semantico por (usuario, organizacion).

Segunda auditoria 2026-11 (#11). `sem_profiles.user_id` era unico en toda la
base: un usuario con pertenencia en varias empresas tenia UN perfil, con el
historial, la carga y la disponibilidad de una sola, y el asignador de la otra
lo leia (o no lo encontraba y chocaba al crearlo).

upgrade:
  * las filas sin organizacion reciben la de ficha de su usuario;
  * se quita el unico de `user_id` (queda un indice normal);
  * nuevo unico `uq_sem_profiles_user_org` (user_id, organization_id).

Idempotente. SQLite (batch recreate) y PostgreSQL. downgrade: no se vuelve al
unico global (fallaria en cuanto un usuario tenga perfil en dos empresas).
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "162_perfil_semantico_por_organizacion"
down_revision: Union[str, None] = "161_jira_hub_a_jira_config"
branch_labels = None
depends_on = None

_TABLA = "sem_profiles"
_NUEVO = "uq_sem_profiles_user_org"
_INDICE = "ix_sem_profiles_user_id"


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if _TABLA not in set(insp.get_table_names()):
        return
    columnas = {c["name"] for c in insp.get_columns(_TABLA)}
    if "organization_id" not in columnas:
        return

    op.execute(sa.text(
        "UPDATE sem_profiles SET organization_id = "
        "(SELECT u.organization_id FROM users u WHERE u.id = sem_profiles.user_id) "
        "WHERE organization_id IS NULL"))

    restr = [u for u in insp.get_unique_constraints(_TABLA)]
    viejos = [u.get("name") for u in restr if u.get("column_names") == ["user_id"]]
    ya_nuevo = any(u.get("name") == _NUEVO for u in restr)
    indices = {i["name"]: i for i in insp.get_indexes(_TABLA)}
    indices_unicos = [n for n, i in indices.items()
                      if i.get("unique") and i.get("column_names") == ["user_id"]
                      and not i.get("duplicates_constraint")]

    with op.batch_alter_table(_TABLA, recreate="auto") as batch:
        for nombre in viejos:
            if nombre:
                batch.drop_constraint(nombre, type_="unique")
        for nombre in indices_unicos:
            batch.drop_index(nombre)
        if _INDICE not in indices or _INDICE in indices_unicos:
            batch.create_index(_INDICE, ["user_id"])
        if not ya_nuevo:
            batch.create_unique_constraint(_NUEVO, ["user_id", "organization_id"])


def downgrade() -> None:
    # Volver al unico global fallaria con un usuario con perfil en dos empresas.
    pass
