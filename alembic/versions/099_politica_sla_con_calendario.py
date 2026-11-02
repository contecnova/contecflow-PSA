"""La politica de SLA elige un calendario de servicio.

Los calendarios de la pagina «Calendarios SLA» (`sla_calendars`, con jornada,
zona, dias y festivos) no los leia ningun calculo de SLA. Ahora una politica
apunta a uno con `calendar_id` y sus vencimientos se cuentan en el.
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "099_politica_sla_con_calendario"
down_revision: Union[str, None] = "098_service_desk_avisos_y_calendario"
branch_labels = None
depends_on = None


def _tiene(conn, tabla: str, columna: str) -> bool:
    return columna in {c["name"] for c in sa.inspect(conn).get_columns(tabla)}


def upgrade() -> None:
    conn = op.get_bind()
    if not _tiene(conn, "sd_sla_policies", "calendar_id"):
        with op.batch_alter_table("sd_sla_policies") as batch:
            batch.add_column(sa.Column("calendar_id", sa.String(36), nullable=True))
            batch.create_foreign_key(
                "fk_sd_sla_policies_calendar_id", "sla_calendars",
                ["calendar_id"], ["id"], ondelete="SET NULL",
            )


def downgrade() -> None:
    conn = op.get_bind()
    if _tiene(conn, "sd_sla_policies", "calendar_id"):
        with op.batch_alter_table("sd_sla_policies") as batch:
            batch.drop_constraint("fk_sd_sla_policies_calendar_id", type_="foreignkey")
            batch.drop_column("calendar_id")
