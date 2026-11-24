"""Grabación con consentimiento de las llamadas con clientes del portal (24-11-2026).

Docs: docs/portal/CHAT_DEL_PORTAL.md §11 (grabación con aviso y consentimiento).

Tabla nueva `portal_call_recording_consents` (modelo
`app/models/grabacion_con_clientes.py`): la evidencia de cada consentimiento
(quién, cuándo, para qué llamada, texto aceptado y su huella, idioma, IP y
navegador, retirada) y el inicio y fin de la grabación de esa ronda, para los
tres chats del portal. `organization_id` NOT NULL (la RLS la aplica `env.py`
tras el `upgrade`); el único lleva `organization_id` delante.

La grabación y la transcripción NO tienen tabla nueva: se reutilizan
`collaboration_recordings` y `collaboration_transcripts` (y el asistente de
reuniones). Los ajustes por empresa van en el grupo en caliente `portal_chat`
(sin esquema).

Compatible con SQLite y Postgres. Idempotente: mira antes la tabla y cada
índice. Deshacer real: borra la tabla (con sus filas).

Revision ID: 214_grabacion_con_consentimiento
Revises: 213_certificaciones_id_semilla
"""
import logging

import sqlalchemy as sa
from alembic import op

revision = "214_grabacion_con_consentimiento"
down_revision = "213_certificaciones_id_semilla"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.214")

TABLA = "portal_call_recording_consents"
_TZ = sa.DateTime(timezone=True)

#: Columnas con `index=True` en el modelo (índice `ix_<tabla>_<columna>`).
INDICES = ("organization_id", "channel", "call_id", "conversation_id", "client_user_id", "proposed_by_user_id",
           "status", "recording_ended_at", "recording_id", "created_at")


def _insp():
    return sa.inspect(op.get_bind())


def _tablas() -> set:
    return set(_insp().get_table_names())


def _indices() -> set:
    if TABLA not in _tablas():
        return set()
    return {i["name"] for i in _insp().get_indexes(TABLA)}


def upgrade() -> None:
    if TABLA not in _tablas():
        op.create_table(
            TABLA,
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                      nullable=False),
            sa.Column("channel", sa.String(20), nullable=False),
            sa.Column("call_id", sa.String(36), nullable=False),
            sa.Column("conversation_id", sa.String(36), nullable=False),
            sa.Column("round", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("client_user_id", sa.String(36), sa.ForeignKey("client_users.id", ondelete="SET NULL"),
                      nullable=True),
            sa.Column("proposed_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"),
                      nullable=True),
            sa.Column("proposed_at", _TZ, server_default=sa.func.now(), nullable=False),
            sa.Column("purpose", sa.String(30), nullable=False, server_default="recording"),
            sa.Column("notice_text", sa.Text(), nullable=False),
            sa.Column("notice_sha256", sa.String(64), nullable=False),
            sa.Column("notice_lang", sa.String(10), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("decided_at", _TZ, nullable=True),
            sa.Column("withdrawn_at", _TZ, nullable=True),
            sa.Column("ip_address", sa.String(64), nullable=True),
            sa.Column("user_agent", sa.String(400), nullable=True),
            sa.Column("recording_started_at", _TZ, nullable=True),
            sa.Column("recording_ended_at", _TZ, nullable=True),
            sa.Column("recording_id", sa.String(36), nullable=True),
            sa.Column("created_at", _TZ, server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("organization_id", "channel", "call_id", "client_user_id", "round",
                                name="uq_portal_rec_consent_round"),
        )
    hechos = _indices()
    for col in INDICES:
        nombre = f"ix_{TABLA}_{col}"
        if nombre not in hechos:
            op.create_index(nombre, TABLA, [col])
    logger.info("214: consentimientos de grabación del portal listos")


def downgrade() -> None:
    if TABLA in _tablas():
        hechos = _indices()
        for col in INDICES:
            nombre = f"ix_{TABLA}_{col}"
            if nombre in hechos:
                op.drop_index(nombre, table_name=TABLA)
        op.drop_table(TABLA)
