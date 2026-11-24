"""Chat en vivo de Soporte completo: adjuntos, reacciones, citas, edición con rastro y llamadas (24-11-2026).

Docs: docs/portal/CHAT_DEL_PORTAL.md §10 (chat en vivo de Soporte).

Columnas nuevas en `sd_channel_messages` (todas nulables):
`reply_to_message_id`, `edited_at`, `deleted_at`, `deleted_by_user_id`,
`deleted_by_client_id`.

Tablas nuevas (todas con `organization_id` NOT NULL; la RLS la aplica
`env.py` tras el `upgrade`), las mismas que el chat del portal (209) sobre las
conversaciones del chat en vivo:

- `sd_channel_message_versions`: texto anterior de cada edición o borrado.
- `sd_channel_attachments`: imágenes y ficheros (clave en el almacén de
  objetos, segmentada por empresa y conversación).
- `sd_channel_reactions`: reacciones con emoji (operador o cliente); únicos con
  `organization_id` delante.
- `sd_channel_calls`: llamadas y videollamadas (solo las inicia el operador; sin
  grabación ni transcripción).

Compatible con SQLite y Postgres (`batch_alter_table` para las columnas).
Idempotente: mira antes cada tabla, columna e índice.

Deshacer real: borra las cuatro tablas (con sus filas; los ficheros del almacén
se quedan) y quita las cinco columnas y sus índices.

Revision ID: 211_chat_en_vivo_completo
Revises: 210_chat_del_portal_colaboracion
"""
import logging

import sqlalchemy as sa
from alembic import op

revision = "211_chat_en_vivo_completo"
down_revision = "210_chat_del_portal_colaboracion"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.211")

_TZ = sa.DateTime(timezone=True)
MENSAJES = "sd_channel_messages"
CONVERSACIONES = "sd_channel_conversations"
#: Orden de creación; el borrado va al revés.
TABLAS = (
    "sd_channel_message_versions",
    "sd_channel_attachments",
    "sd_channel_reactions",
    "sd_channel_calls",
)


def _insp():
    return sa.inspect(op.get_bind())


def _tablas() -> set:
    return set(_insp().get_table_names())


def _cols(tabla: str) -> set:
    if tabla not in _tablas():
        return set()
    return {c["name"] for c in _insp().get_columns(tabla)}


def _indices(tabla: str) -> set:
    if tabla not in _tablas():
        return set()
    return {i["name"] for i in _insp().get_indexes(tabla)}


def _id():
    return sa.Column("id", sa.String(36), primary_key=True)


def _org():
    return sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                     nullable=False)


def _fk(nombre: str, destino: str, ondelete: str = "SET NULL", nullable: bool = True):
    return sa.Column(nombre, sa.String(36), sa.ForeignKey(f"{destino}.id", ondelete=ondelete), nullable=nullable)


def _definicion() -> dict:
    """La misma que `app/models/service_desk/mercado.py`."""
    return {
        "sd_channel_message_versions": [
            _id(), _org(),
            _fk("conversation_id", CONVERSACIONES, "CASCADE", nullable=False),
            _fk("message_id", MENSAJES, "CASCADE", nullable=False),
            sa.Column("body", sa.Text(), nullable=True),
            sa.Column("change_type", sa.String(10), nullable=False, server_default="edit"),
            _fk("edited_by_user_id", "users"),
            _fk("edited_by_client_id", "client_users"),
            sa.Column("edited_at", _TZ, server_default=sa.func.now(), nullable=False),
        ],
        "sd_channel_attachments": [
            _id(), _org(),
            _fk("conversation_id", CONVERSACIONES, "CASCADE", nullable=False),
            _fk("message_id", MENSAJES, "CASCADE"),
            _fk("uploaded_by_user_id", "users"),
            _fk("uploaded_by_client_id", "client_users"),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("mime_type", sa.String(160), nullable=True),
            sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("storage_provider", sa.String(40), nullable=False, server_default="local"),
            sa.Column("storage_key", sa.String(800), nullable=False),
            sa.Column("sha256", sa.String(64), nullable=True),
            sa.Column("av_status", sa.String(40), nullable=False, server_default="pending"),
            sa.Column("dlp_status", sa.String(40), nullable=False, server_default="pending"),
            sa.Column("is_quarantined", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", _TZ, server_default=sa.func.now(), nullable=False),
            sa.Column("deleted_at", _TZ, nullable=True),
        ],
        "sd_channel_reactions": [
            _id(), _org(),
            _fk("conversation_id", CONVERSACIONES, "CASCADE", nullable=False),
            _fk("message_id", MENSAJES, "CASCADE", nullable=False),
            _fk("user_id", "users", "CASCADE"),
            _fk("client_user_id", "client_users", "CASCADE"),
            sa.Column("emoji", sa.String(32), nullable=False),
            sa.Column("created_at", _TZ, server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("organization_id", "message_id", "user_id", "emoji", name="uq_sd_channel_reaction_user"),
            sa.UniqueConstraint("organization_id", "message_id", "client_user_id", "emoji",
                                name="uq_sd_channel_reaction_client"),
        ],
        "sd_channel_calls": [
            _id(), _org(),
            _fk("conversation_id", CONVERSACIONES, "CASCADE", nullable=False),
            _fk("initiated_by_user_id", "users"),
            sa.Column("kind", sa.String(10), nullable=False, server_default="audio"),
            sa.Column("status", sa.String(20), nullable=False, server_default="ringing"),
            sa.Column("livekit_room", sa.String(160), nullable=False),
            _fk("answered_by_client_id", "client_users"),
            _fk("declined_by_client_id", "client_users"),
            _fk("ended_by_user_id", "users"),
            _fk("ended_by_client_id", "client_users"),
            sa.Column("created_at", _TZ, server_default=sa.func.now(), nullable=False),
            sa.Column("answered_at", _TZ, nullable=True),
            sa.Column("ended_at", _TZ, nullable=True),
            sa.Column("duration_seconds", sa.Integer(), nullable=False, server_default="0"),
        ],
    }


#: Columnas con `index=True` en el modelo (índice `ix_<tabla>_<columna>`).
INDICES = {
    "sd_channel_message_versions": ("organization_id", "conversation_id", "message_id", "edited_by_user_id",
                                    "edited_by_client_id"),
    "sd_channel_attachments": ("organization_id", "conversation_id", "message_id", "uploaded_by_user_id",
                               "uploaded_by_client_id", "created_at"),
    "sd_channel_reactions": ("organization_id", "conversation_id", "message_id", "user_id", "client_user_id"),
    "sd_channel_calls": ("organization_id", "conversation_id", "initiated_by_user_id", "status",
                         "answered_by_client_id", "declined_by_client_id", "ended_by_user_id",
                         "ended_by_client_id", "created_at"),
}

COLUMNAS_DE_MENSAJE = ("reply_to_message_id", "edited_at", "deleted_at", "deleted_by_user_id", "deleted_by_client_id")
INDICES_DE_MENSAJE = ("reply_to_message_id", "deleted_at", "deleted_by_user_id", "deleted_by_client_id")


def upgrade() -> None:
    if MENSAJES in _tablas():
        faltan = [c for c in COLUMNAS_DE_MENSAJE if c not in _cols(MENSAJES)]
        if faltan:
            with op.batch_alter_table(MENSAJES) as b:
                if "reply_to_message_id" in faltan:
                    b.add_column(sa.Column("reply_to_message_id", sa.String(36),
                                           sa.ForeignKey("sd_channel_messages.id", ondelete="SET NULL",
                                                         name="fk_sd_channel_msg_reply_to"),
                                           nullable=True))
                if "edited_at" in faltan:
                    b.add_column(sa.Column("edited_at", _TZ, nullable=True))
                if "deleted_at" in faltan:
                    b.add_column(sa.Column("deleted_at", _TZ, nullable=True))
                if "deleted_by_user_id" in faltan:
                    b.add_column(sa.Column("deleted_by_user_id", sa.String(36),
                                           sa.ForeignKey("users.id", ondelete="SET NULL",
                                                         name="fk_sd_channel_msg_deleted_by_user"),
                                           nullable=True))
                if "deleted_by_client_id" in faltan:
                    b.add_column(sa.Column("deleted_by_client_id", sa.String(36),
                                           sa.ForeignKey("client_users.id", ondelete="SET NULL",
                                                         name="fk_sd_channel_msg_deleted_by_client"),
                                           nullable=True))
        hechos = _indices(MENSAJES)
        for col in INDICES_DE_MENSAJE:
            nombre = f"ix_{MENSAJES}_{col}"
            if nombre not in hechos:
                op.create_index(nombre, MENSAJES, [col])

    definicion = _definicion()
    for tabla in TABLAS:
        if tabla not in _tablas():
            op.create_table(tabla, *definicion[tabla])
        hechos = _indices(tabla)
        for col in INDICES[tabla]:
            nombre = f"ix_{tabla}_{col}"
            if nombre not in hechos:
                op.create_index(nombre, tabla, [col])
    logger.info("211: chat en vivo completo listo")


def downgrade() -> None:
    for tabla in reversed(TABLAS):
        if tabla in _tablas():
            op.drop_table(tabla)
    if MENSAJES in _tablas():
        hechos = _indices(MENSAJES)
        for col in INDICES_DE_MENSAJE:
            nombre = f"ix_{MENSAJES}_{col}"
            if nombre in hechos:
                op.drop_index(nombre, table_name=MENSAJES)
        presentes = [c for c in COLUMNAS_DE_MENSAJE if c in _cols(MENSAJES)]
        if presentes:
            with op.batch_alter_table(MENSAJES) as b:
                for c in presentes:
                    b.drop_column(c)
