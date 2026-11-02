"""Alertas de monitorizacion: cada una abre (o agrupa) una incidencia.

Antes no habia entrada de alertas: la «correlacion de alertas» agrupaba tickets
ya abiertos. `sd_monitoring_alerts` guarda cada alerta, su incidencia y sus
repeticiones, para no abrir una por cada aviso del mismo fallo.
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "104_alertas_de_monitorizacion"
down_revision: Union[str, None] = "103_cambios_comite_calendario_versiones"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "sd_monitoring_alerts" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "sd_monitoring_alerts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("dedupe_key", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="firing"),
        sa.Column("severity", sa.String(30), nullable=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("ci_id", sa.String(36), sa.ForeignKey("sd_configuration_items.id", ondelete="SET NULL"), nullable=True),
        sa.Column("ticket_id", sa.String(36), sa.ForeignKey("sd_tickets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("occurrences", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    for col in ("organization_id", "dedupe_key", "status", "ticket_id"):
        op.create_index(f"ix_sd_monitoring_alerts_{col}", "sd_monitoring_alerts", [col])


def downgrade() -> None:
    if "sd_monitoring_alerts" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("sd_monitoring_alerts")
