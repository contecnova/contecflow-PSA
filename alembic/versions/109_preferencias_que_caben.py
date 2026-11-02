"""Tema y densidad de las preferencias: caben todos los valores.

`user_preferences.theme_mode` y `ui_density` eran `String(10)`: en Postgres
el tema `high-contrast` (13) y la densidad `comfortable` (11) fallaban al
guardar. Se ensanchan a 20.
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "109_preferencias_que_caben"
down_revision: Union[str, None] = "108_ola_de_las_colas"
branch_labels = None
depends_on = None

_COLUMNAS = ("theme_mode", "ui_density")


def upgrade() -> None:
    with op.batch_alter_table("user_preferences") as batch:
        for c in _COLUMNAS:
            batch.alter_column(c, existing_type=sa.String(10), type_=sa.String(20), existing_nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("user_preferences") as batch:
        for c in _COLUMNAS:
            batch.alter_column(c, existing_type=sa.String(20), type_=sa.String(10), existing_nullable=True)
