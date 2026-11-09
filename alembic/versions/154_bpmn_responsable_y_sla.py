"""BPM: responsable y SLA de un proceso.

Revisión 2026-11. «Nuevo proceso» pedía responsable y SLA y no se guardaban:
`bpmn_processes` no tenía dónde, y se perdían al recargar.

Revision ID: 154_bpmn_responsable_y_sla
Revises: 153_webhook_logs_sin_secretos
"""
import sqlalchemy as sa
from alembic import op

revision = "154_bpmn_responsable_y_sla"
down_revision = "153_webhook_logs_sin_secretos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    con = op.get_bind()
    if "bpmn_processes" not in sa.inspect(con).get_table_names():
        return
    columnas = {c["name"] for c in sa.inspect(con).get_columns("bpmn_processes")}
    with op.batch_alter_table("bpmn_processes") as t:
        if "owner" not in columnas:
            t.add_column(sa.Column("owner", sa.String(200), nullable=True))
        if "sla" not in columnas:
            t.add_column(sa.Column("sla", sa.String(120), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("bpmn_processes") as t:
        t.drop_column("sla")
        t.drop_column("owner")
