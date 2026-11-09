"""Logs de webhooks entrantes sin credenciales.

Revisión 2026-11. `POST /webhooks/fire/{slug}` guardaba todas las cabeceras de la
petición (Authorization, Cookie, la firma). El código ya las tapa al guardar;
esto tapa las que ya estaban en `webhook_trigger_logs.headers`.

Revision ID: 153_webhook_logs_sin_secretos
Revises: 152_presupuestos_seguir_a_fondo
"""
import json

import sqlalchemy as sa
from alembic import op

revision = "153_webhook_logs_sin_secretos"
down_revision = "152_presupuestos_seguir_a_fondo"
branch_labels = None
depends_on = None

_SENSIBLES = ("authorization", "cookie", "signature", "token", "secret", "api-key", "apikey", "password", "x-auth")


def upgrade() -> None:
    con = op.get_bind()
    if "webhook_trigger_logs" not in sa.inspect(con).get_table_names():
        return
    filas = con.execute(sa.text("SELECT id, headers FROM webhook_trigger_logs WHERE headers IS NOT NULL")).fetchall()
    for id_, crudo in filas:
        try:
            cabeceras = json.loads(crudo)
        except ValueError:      # truncado a 1.000 caracteres: no se puede separar lo sensible
            con.execute(sa.text("UPDATE webhook_trigger_logs SET headers = NULL WHERE id = :i"), {"i": id_})
            continue
        if not isinstance(cabeceras, dict):
            continue
        limpias = {k: ("[oculto]" if any(x in k.lower() for x in _SENSIBLES) else v) for k, v in cabeceras.items()}
        if limpias != cabeceras:
            con.execute(sa.text("UPDATE webhook_trigger_logs SET headers = :h WHERE id = :i"),
                        {"h": json.dumps(limpias), "i": id_})


def downgrade() -> None:
    pass    # lo tapado no se recupera
