"""Chat del portal completo: adjuntos, reacciones, edición con rastro y llamadas (24-11-2026).

Docs: docs/portal/CHAT_DEL_PORTAL.md (funcionalidades, «solo el operador llama»,
seguridad de ficheros y GRC).

Columnas nuevas en `portal_conversation_messages` (todas nulables):
`edited_at`, `deleted_at`, `deleted_by_user_id`, `deleted_by_client_id`.

Tablas nuevas (todas con `organization_id` NOT NULL, como exige la 208; la RLS
la aplica `env.py` tras el `upgrade`):

- `portal_conversation_message_versions`: texto anterior de cada edición o
  borrado (el rastro que ve el equipo).
- `portal_conversation_attachments`: imágenes y ficheros (clave en el almacén
  de objetos, segmentada por empresa y conversación).
- `portal_conversation_reactions`: reacciones con emoji (de equipo o cliente).
- `portal_conversation_calls`: llamadas y videollamadas (solo las inicia el
  equipo; sin grabación ni transcripción).

Compatible con SQLite y Postgres (`batch_alter_table` para las columnas).
Idempotente: mira antes cada tabla, columna e índice.

Deshacer real: borra las cuatro tablas (con sus filas; los ficheros del almacén
se quedan: el deshacer no toca el almacén) y quita las cuatro columnas.

Revision ID: 209_chat_del_portal_completo
Revises: 208_empresa_obligatoria_y_portal
"""
import logging

import sqlalchemy as sa
from alembic import op

revision = "209_chat_del_portal_completo"
down_revision = "208_empresa_obligatoria_y_portal"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.209")

_TZ = sa.DateTime(timezone=True)
MENSAJES = "portal_conversation_messages"
#: Orden de creación; el borrado va al revés.
TABLAS = (
    "portal_conversation_message_versions",
    "portal_conversation_attachments",
    "portal_conversation_reactions",
    "portal_conversation_calls",
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
    """La misma que `app/models/portal_conversations.py`."""
    return {
        "portal_conversation_message_versions": [
            _id(), _org(),
            _fk("message_id", MENSAJES, "CASCADE", nullable=False),
            sa.Column("body", sa.Text(), nullable=True),
            sa.Column("raw_body", sa.Text(), nullable=True),
            sa.Column("change_type", sa.String(10), nullable=False, server_default="edit"),
            _fk("edited_by_user_id", "users"),
            _fk("edited_by_client_id", "client_users"),
            sa.Column("edited_at", _TZ, server_default=sa.func.now(), nullable=False),
        ],
        "portal_conversation_attachments": [
            _id(), _org(),
            _fk("conversation_id", "portal_conversations", "CASCADE", nullable=False),
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
        "portal_conversation_reactions": [
            _id(), _org(),
            _fk("message_id", MENSAJES, "CASCADE", nullable=False),
            _fk("user_id", "users", "CASCADE"),
            _fk("client_user_id", "client_users", "CASCADE"),
            sa.Column("emoji", sa.String(32), nullable=False),
            sa.Column("created_at", _TZ, server_default=sa.func.now(), nullable=False),
            # Únicos por empresa (24-11-2026, prueba general: tests/test_unicos_por_organizacion.py).
            sa.UniqueConstraint("organization_id", "message_id", "user_id", "emoji", name="uq_portal_conv_reaction_user"),
            sa.UniqueConstraint("organization_id", "message_id", "client_user_id", "emoji", name="uq_portal_conv_reaction_client"),
        ],
        "portal_conversation_calls": [
            _id(), _org(),
            _fk("conversation_id", "portal_conversations", "CASCADE", nullable=False),
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
    "portal_conversation_message_versions": ("organization_id", "message_id", "edited_by_user_id",
                                             "edited_by_client_id"),
    "portal_conversation_attachments": ("organization_id", "conversation_id", "message_id", "uploaded_by_user_id",
                                        "uploaded_by_client_id", "created_at"),
    "portal_conversation_reactions": ("organization_id", "message_id", "user_id", "client_user_id"),
    "portal_conversation_calls": ("organization_id", "conversation_id", "initiated_by_user_id", "status",
                                  "answered_by_client_id", "declined_by_client_id", "ended_by_user_id",
                                  "ended_by_client_id", "created_at"),
}

COLUMNAS_DE_MENSAJE = ("edited_at", "deleted_at", "deleted_by_user_id", "deleted_by_client_id")
INDICES_DE_MENSAJE = ("deleted_at", "deleted_by_user_id", "deleted_by_client_id")


def upgrade() -> None:
    if MENSAJES in _tablas():
        faltan = [c for c in COLUMNAS_DE_MENSAJE if c not in _cols(MENSAJES)]
        if faltan:
            with op.batch_alter_table(MENSAJES) as b:
                if "edited_at" in faltan:
                    b.add_column(sa.Column("edited_at", _TZ, nullable=True))
                if "deleted_at" in faltan:
                    b.add_column(sa.Column("deleted_at", _TZ, nullable=True))
                if "deleted_by_user_id" in faltan:
                    b.add_column(sa.Column("deleted_by_user_id", sa.String(36),
                                           sa.ForeignKey("users.id", ondelete="SET NULL",
                                                         name="fk_portal_conv_msg_deleted_by_user"),
                                           nullable=True))
                if "deleted_by_client_id" in faltan:
                    b.add_column(sa.Column("deleted_by_client_id", sa.String(36),
                                           sa.ForeignKey("client_users.id", ondelete="SET NULL",
                                                         name="fk_portal_conv_msg_deleted_by_client"),
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
    logger.info("209: chat del portal completo listo")


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
