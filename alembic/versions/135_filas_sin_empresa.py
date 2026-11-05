"""Filas sin empresa que la empresa no veía: se recolocan desde su propio registro.

Revisión 2026-11. Medido en la base de un despliegue (379 tablas recorridas):
filas sin `organization_id` en tablas estrictas, invisibles para los usuarios de
su empresa. Cada una se recoloca desde lo que la define, sin adivinar:

- ai_messages → la empresa de su conversación;
- ai_predictions → la de su ticket, proyecto o usuario;
- sso_configs → la de quien la creó;
- sd_itsm_metric_snapshots sin empresa → se borran: mezclaban los tickets de
  todas las empresas y no se pueden atribuir; ahora se calculan una por empresa.

Los tipos de cambio sin empresa son globales a propósito (el modelo los incluye
para todas) y la matriz GRC sin empresa son los valores por defecto: no se tocan.
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "135_filas_sin_empresa"
down_revision: Union[str, None] = "134_mcp_acciones_pendientes"
branch_labels = None
depends_on = None

_DESDE = {
    "ai_messages": "(SELECT c.organization_id FROM ai_conversations c WHERE c.id = ai_messages.conversation_id)",
    "sso_configs": "(SELECT u.organization_id FROM users u WHERE u.id = sso_configs.created_by)",
}
_PREDICCIONES = {
    "ticket": "(SELECT t.organization_id FROM sd_tickets t WHERE t.id = ai_predictions.entity_id)",
    "project": "(SELECT p.organization_id FROM projects p WHERE p.id = ai_predictions.entity_id)",
    "user": "(SELECT u.organization_id FROM users u WHERE u.id = ai_predictions.entity_id)",
}


def upgrade() -> None:
    tablas = set(sa.inspect(op.get_bind()).get_table_names())
    for tabla, origen in _DESDE.items():
        if tabla in tablas:
            op.execute(f"UPDATE {tabla} SET organization_id = {origen} WHERE organization_id IS NULL")
    if "ai_predictions" in tablas:
        for tipo, origen in _PREDICCIONES.items():
            op.execute(f"UPDATE ai_predictions SET organization_id = {origen} "
                       f"WHERE organization_id IS NULL AND entity_type = '{tipo}'")
    if "sd_itsm_metric_snapshots" in tablas:
        op.execute("DELETE FROM sd_itsm_metric_snapshots WHERE organization_id IS NULL")


def downgrade() -> None:
    pass   # recolocar datos no se deshace
