"""Correo entrante: registro de mensajes ya procesados.

El buzon se lee cada pocos minutos y los webhooks de las pasarelas se
reintentan; `sd_inbound_messages` impide que el mismo correo abra dos tickets.
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "101_correo_entrante"
down_revision: Union[str, None] = "100_numeracion_por_organizacion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "sd_inbound_messages" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "sd_inbound_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("message_id", sa.String(255), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False, server_default="email"),
        sa.Column("sender", sa.String(255), nullable=True),
        sa.Column("ticket_id", sa.String(36), sa.ForeignKey("sd_tickets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "message_id", name="uq_sd_inbound_org_message"),
    )
    op.create_index("ix_sd_inbound_messages_organization_id", "sd_inbound_messages", ["organization_id"])
    op.create_index("ix_sd_inbound_messages_ticket_id", "sd_inbound_messages", ["ticket_id"])
    op.create_index("ix_sd_inbound_messages_received_at", "sd_inbound_messages", ["received_at"])


def downgrade() -> None:
    if "sd_inbound_messages" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("sd_inbound_messages")
