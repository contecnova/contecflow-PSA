"""El acento del perfil, vacío por defecto: manda el del tema.

Auditoría 2026-11: `user_preferences.accent_color` nacía con `#4f8ef7` y el
servicio lo devolvía cuando faltaba, así que se escribía siempre en `<html>` y
tapaba el acento de cada tema: ningún usuario con sesión veía el dorado de
`freight`. El valor guardado no distingue «lo eligió» de «vino por defecto»;
se vacía. Quien eligiera Índigo (el mismo color) vuelve al acento del tema,
que en `dark` es ese mismo.
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "112_acento_del_tema"
down_revision: Union[str, None] = "111_un_solo_inventario"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("user_preferences") as batch:
        batch.alter_column("accent_color", existing_type=sa.String(20), server_default=None, existing_nullable=True)
    op.execute("UPDATE user_preferences SET accent_color = NULL WHERE lower(accent_color) = '#4f8ef7'")


def downgrade() -> None:
    pass
