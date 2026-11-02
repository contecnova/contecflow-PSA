"""Tareas de cumplimiento de los servicios del catalogo.

`sd_service_items.fulfillment_tasks`: lo que hay que hacer para servir la
peticion, cada cosa en su cola. Antes el cumplimiento era manual.
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "107_tareas_de_cumplimiento"
down_revision: Union[str, None] = "106_tiempo_de_ticket_a_partes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("sd_service_items")}
    if "fulfillment_tasks" not in cols:
        with op.batch_alter_table("sd_service_items") as batch:
            batch.add_column(sa.Column("fulfillment_tasks", sa.Text(), nullable=True))


def downgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("sd_service_items")}
    if "fulfillment_tasks" in cols:
        with op.batch_alter_table("sd_service_items") as batch:
            batch.drop_column("fulfillment_tasks")
