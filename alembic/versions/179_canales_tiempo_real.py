"""Canales en tiempo real: hilos de Slack, adjuntos de WhatsApp, chat inmediato
del portal y asistente con IA (17-11-2026).

Columnas nuevas:

- `sd_channel_conversations`:
  - `client_read_at` / `agent_read_at`: hasta cuando ha leido cada lado (el
    «leido» del chat en vivo; lo marca el WebSocket).
  - `last_inbound_at`: ultimo mensaje del cliente. En WhatsApp abre la ventana
    de 24 h de Meta: fuera de ella solo salen plantillas.
- `sd_channel_messages`:
  - `ticket_comment_id`: el comentario del ticket que es (o que lo origino).
    Evita bucles y duplicados: un comentario que ya salio por ese canal, o que
    entro por el, no se vuelve a enviar.
  - `attachment_document_id`: el adjunto (documento del ticket) que lleva.
  - `delivery_status`: `sent` | `template` | `failed` | `outside_window`.
- `sd_portal_assistant_actions.engine`: `ai` o `rules` (quien entendio la
  peticion), para la auditoria del asistente.

Downgrade: quita las columnas.

Revision ID: 179_canales_tiempo_real
Revises: 178_externos_como_internos
"""
import sqlalchemy as sa
from alembic import op

revision = "179_canales_tiempo_real"
down_revision = "178_externos_como_internos"
branch_labels = None
depends_on = None


def _columnas(con, tabla: str) -> set[str]:
    return {c["name"] for c in sa.inspect(con).get_columns(tabla)}


def _indices(con, tabla: str) -> set[str]:
    return {i["name"] for i in sa.inspect(con).get_indexes(tabla)}


def upgrade() -> None:
    con = op.get_bind()
    conv = _columnas(con, "sd_channel_conversations")
    with op.batch_alter_table("sd_channel_conversations") as b:
        for nombre in ("client_read_at", "agent_read_at", "last_inbound_at"):
            if nombre not in conv:
                b.add_column(sa.Column(nombre, sa.DateTime(timezone=True), nullable=True))

    msg = _columnas(con, "sd_channel_messages")
    with op.batch_alter_table("sd_channel_messages") as b:
        if "ticket_comment_id" not in msg:
            b.add_column(sa.Column("ticket_comment_id", sa.String(36), nullable=True))
            b.create_foreign_key("fk_sd_channel_messages_comment", "sd_ticket_comments",
                                 ["ticket_comment_id"], ["id"], ondelete="SET NULL")
        if "attachment_document_id" not in msg:
            b.add_column(sa.Column("attachment_document_id", sa.String(36), nullable=True))
            b.create_foreign_key("fk_sd_channel_messages_document", "documents",
                                 ["attachment_document_id"], ["id"], ondelete="SET NULL")
        if "delivery_status" not in msg:
            b.add_column(sa.Column("delivery_status", sa.String(20), nullable=True))
    if "ix_sd_channel_messages_ticket_comment_id" not in _indices(con, "sd_channel_messages"):
        op.create_index("ix_sd_channel_messages_ticket_comment_id", "sd_channel_messages", ["ticket_comment_id"])

    if "engine" not in _columnas(con, "sd_portal_assistant_actions"):
        with op.batch_alter_table("sd_portal_assistant_actions") as b:
            b.add_column(sa.Column("engine", sa.String(10), nullable=True))

    # Ventana de WhatsApp de las conversaciones abiertas: su ultimo mensaje entrante.
    op.execute(
        "UPDATE sd_channel_conversations SET last_inbound_at = ("
        " SELECT MAX(m.created_at) FROM sd_channel_messages m"
        " WHERE m.conversation_id = sd_channel_conversations.id AND m.direction = 'in')"
        " WHERE last_inbound_at IS NULL"
    )


def downgrade() -> None:
    con = op.get_bind()
    if "engine" in _columnas(con, "sd_portal_assistant_actions"):
        with op.batch_alter_table("sd_portal_assistant_actions") as b:
            b.drop_column("engine")
    if "ix_sd_channel_messages_ticket_comment_id" in _indices(con, "sd_channel_messages"):
        op.drop_index("ix_sd_channel_messages_ticket_comment_id", table_name="sd_channel_messages")
    msg = _columnas(con, "sd_channel_messages")
    with op.batch_alter_table("sd_channel_messages") as b:
        if "delivery_status" in msg:
            b.drop_column("delivery_status")
        if "attachment_document_id" in msg:
            b.drop_constraint("fk_sd_channel_messages_document", type_="foreignkey")
            b.drop_column("attachment_document_id")
        if "ticket_comment_id" in msg:
            b.drop_constraint("fk_sd_channel_messages_comment", type_="foreignkey")
            b.drop_column("ticket_comment_id")
    conv = _columnas(con, "sd_channel_conversations")
    with op.batch_alter_table("sd_channel_conversations") as b:
        for nombre in ("last_inbound_at", "agent_read_at", "client_read_at"):
            if nombre in conv:
                b.drop_column(nombre)
