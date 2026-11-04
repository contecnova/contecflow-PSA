"""Integraciones: se borran los datos inventados por las sincronizaciones simuladas.

Revision 2026-11. Hasta este cambio, «Sync» en Enterprise → Integraciones no
llamaba a ningun servicio:

- GitHub/GitLab creaba en las cinco primeras tareas enlaces a commits que no
  existen (`external_id` «demo_<codigo>», url «…/commit/abc123def456», autor
  «developer@empresa.com»);
- Google Calendar/Outlook guardaba un evento por sprint (`external_id`
  «contecflow_sprint_<id>») marcado como enviado, sin enviarlo a ningun sitio.

Ahora las sincronizaciones son reales (`cab_service.sync_*`). Esta migracion
quita esas filas para que nada las tome por datos del proveedor. No toca los
eventos enviados de verdad: su `external_id` es el id que devuelve Google.
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "124_integraciones_reales"
down_revision: Union[str, None] = "123_filas_sin_organizacion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    tablas = set(sa.inspect(bind).get_table_names())
    if "commit_links" in tablas:
        bind.execute(sa.text(
            "DELETE FROM commit_links WHERE external_id LIKE 'demo\\_%' ESCAPE '\\' "
            "AND url LIKE '%/commit/abc123def456'"))
    if "calendar_events" in tablas:
        bind.execute(sa.text(
            "DELETE FROM calendar_events WHERE external_id LIKE 'contecflow\\_sprint\\_%' ESCAPE '\\'"))


def downgrade() -> None:
    # Lo borrado era inventado: no hay nada que restaurar.
    pass
