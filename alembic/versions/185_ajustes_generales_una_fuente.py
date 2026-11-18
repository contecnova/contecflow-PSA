"""Ajustes generales con una sola fuente (18-11-2026).

La pantalla General guardaba moneda, zona horaria, idioma y jornada en las filas
`app_settings` con claves `currency`, `timezone`, `language` y
`work_hours_per_day`, que no leía ningún servicio: lo que usa la aplicación son
las claves de ejecución `DEFAULT_CURRENCY`, `DEFAULT_TIMEZONE`,
`DEFAULT_LANGUAGE` y `DEFAULT_WORKING_HOURS_PER_DAY` (grupo `locale`, las de
`GET /settings/org-defaults`). Desde esta revisión `/settings/general` lee y
escribe esas claves (`ALIAS_DE_EJECUCION` en
`app/services/settings_service/generales.py`).

Datos:
- Una fila de EMPRESA con el alias (alguien lo cambió en General) se copia a la
  clave de ejecución de esa empresa si la empresa no tiene ya una propia: se
  respeta lo que se pidió en pantalla.
- Las filas GLOBALES del alias no se copian: las sembraba el arranque con el
  valor del entorno, y copiarlas fijaría como ajuste lo que hoy es el entorno.
- Después se borran todas las filas del alias (ya no se siembran).

Sin cambios de esquema. Downgrade: no restaura las filas borradas (la API sigue
sirviendo los alias desde las claves de ejecución, así que no hace falta).

Revision ID: 185_ajustes_generales_una_fuente
Revises: 184_horas_extra
"""
import uuid

import sqlalchemy as sa
from alembic import op

revision = "185_ajustes_generales_una_fuente"
down_revision = "184_horas_extra"
branch_labels = None
depends_on = None

ALIAS = {
    "currency": "DEFAULT_CURRENCY",
    "timezone": "DEFAULT_TIMEZONE",
    "language": "DEFAULT_LANGUAGE",
    "work_hours_per_day": "DEFAULT_WORKING_HOURS_PER_DAY",
}


def upgrade() -> None:
    bind = op.get_bind()
    if "app_settings" not in set(sa.inspect(bind).get_table_names()):
        return
    filas = bind.execute(sa.text(
        "SELECT key, value, organization_id FROM app_settings "
        "WHERE key IN :claves AND organization_id IS NOT NULL"
    ).bindparams(sa.bindparam("claves", expanding=True)), {"claves": list(ALIAS)}).fetchall()
    for key, value, org in filas:
        destino = ALIAS[key]
        ya = bind.execute(sa.text(
            "SELECT 1 FROM app_settings WHERE key = :k AND organization_id = :o"
        ), {"k": destino, "o": org}).first()
        if ya is None and value not in (None, ""):
            bind.execute(sa.text(
                "INSERT INTO app_settings (id, organization_id, key, value) VALUES (:id, :o, :k, :v)"
            ), {"id": str(uuid.uuid4()), "o": org, "k": destino, "v": str(value)})
    bind.execute(sa.text("DELETE FROM app_settings WHERE key IN :claves").bindparams(
        sa.bindparam("claves", expanding=True)), {"claves": list(ALIAS)})


def downgrade() -> None:
    pass
