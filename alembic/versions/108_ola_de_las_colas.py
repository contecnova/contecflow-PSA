"""OLA de las colas de soporte.

`sd_agent_groups.ola_hours`: el objetivo interno de cada cola. En el ticket,
cuando entro en su cola (`group_assigned_at`), cuando vence (`ola_due`), la
pausa que ya llevaba al entrar (`ola_pause_base`) y si se incumplio.

Los tickets abiertos que ya tienen cola empiezan a contar desde esta
migracion: no se sabe cuando entraron.
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "108_ola_de_las_colas"
down_revision: Union[str, None] = "107_tareas_de_cumplimiento"
branch_labels = None
depends_on = None

_TICKET = (
    ("group_assigned_at", lambda: sa.Column("group_assigned_at", sa.DateTime(timezone=True), nullable=True)),
    ("ola_due", lambda: sa.Column("ola_due", sa.DateTime(timezone=True), nullable=True)),
    ("ola_pause_base", lambda: sa.Column("ola_pause_base", sa.Integer(), nullable=True)),
    ("ola_breached", lambda: sa.Column("ola_breached", sa.Boolean(), nullable=False, server_default=sa.false())),
)


def _columnas(tabla: str) -> set:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(tabla)}


def upgrade() -> None:
    if "ola_hours" not in _columnas("sd_agent_groups"):
        with op.batch_alter_table("sd_agent_groups") as batch:
            batch.add_column(sa.Column("ola_hours", sa.Float(), nullable=True))
    faltan = [c for nombre, c in _TICKET if nombre not in _columnas("sd_tickets")]
    if faltan:
        with op.batch_alter_table("sd_tickets") as batch:
            for c in faltan:
                batch.add_column(c())
    op.execute(
        "UPDATE sd_tickets SET group_assigned_at = CURRENT_TIMESTAMP, "
        "ola_pause_base = COALESCE(sla_pause_minutes, 0) "
        "WHERE assigned_group_id IS NOT NULL AND group_assigned_at IS NULL "
        "AND status IN ('new', 'assigned', 'in_progress', 'pending_client', 'pending_third')"
    )


def downgrade() -> None:
    with op.batch_alter_table("sd_tickets") as batch:
        for nombre, _ in _TICKET:
            if nombre in _columnas("sd_tickets"):
                batch.drop_column(nombre)
    if "ola_hours" in _columnas("sd_agent_groups"):
        with op.batch_alter_table("sd_agent_groups") as batch:
            batch.drop_column("ola_hours")
