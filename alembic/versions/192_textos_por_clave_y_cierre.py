"""Textos guardados por clave: historial del ticket y nota del agente autónomo (19-11-2026).

Hasta ahora `sd_ticket_history.new_value` y
`sd_autonomous_playbook_executions.resolution_note` guardaban el texto ya
escrito en el idioma de quien lo generó (o en inglés fijo: «Possible duplicate
of…», «[Auto-resolved]…»), y así lo veía todo el mundo. Ahora se guarda además
la clave de `app/services/textos_de_salida.py` y sus datos, y al leer se pinta
en el idioma de quien mira. El texto guardado se queda como respaldo (filas de
antes, clave desconocida) y para quien lea la tabla en crudo.

Columnas nuevas (ninguna tabla nueva):

- `sd_ticket_history.new_value_key` (String 120) y `new_value_params` (Text, JSON).
- `sd_autonomous_playbook_executions.resolution_note_key` (String 120) y
  `resolution_note_params` (Text, JSON).

Sin datos personales nuevos: los parámetros son números de ticket, de artículo
de la KB, confianza o id del playbook (lo mismo que ya había en el texto).
Retención: la de su fila (historial del ticket, registro del agente).

Idempotente: cada columna se crea solo si no existe. Downgrade: las quita
(el texto guardado sigue ahí, solo se pierde la traducción al leer).

Revision ID: 192_textos_por_clave_y_cierre
Revises: 191_proveedores_portal_y_aprobacion
"""
import sqlalchemy as sa
from alembic import op

revision = "192_textos_por_clave_y_cierre"
down_revision = "191_proveedores_portal_y_aprobacion"
branch_labels = None
depends_on = None

COLUMNAS = (
    ("sd_ticket_history", sa.Column("new_value_key", sa.String(120), nullable=True)),
    ("sd_ticket_history", sa.Column("new_value_params", sa.Text(), nullable=True)),
    ("sd_autonomous_playbook_executions", sa.Column("resolution_note_key", sa.String(120), nullable=True)),
    ("sd_autonomous_playbook_executions", sa.Column("resolution_note_params", sa.Text(), nullable=True)),
)


def _existe(tabla: str) -> bool:
    return tabla in sa.inspect(op.get_bind()).get_table_names()


def _columnas(tabla: str) -> set:
    if not _existe(tabla):
        return set()
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(tabla)}


def upgrade() -> None:
    for tabla, columna in COLUMNAS:
        if _existe(tabla) and columna.name not in _columnas(tabla):
            op.add_column(tabla, columna.copy())


def downgrade() -> None:
    for tabla, columna in reversed(COLUMNAS):
        if columna.name in _columnas(tabla):
            with op.batch_alter_table(tabla) as b:
                b.drop_column(columna.name)
