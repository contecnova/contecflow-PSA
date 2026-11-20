"""Asistente de reuniones: Teams/Zoom/Meet, bot invitado, grabación propia y GRC (19-11-2026).

Diseño: `docs/ASISTENTE_DE_REUNIONES.md`. Modelos: `app/models/ai_chat.py`
(`AIMeeting`, `AIMeetingAction` ampliados) y `app/models/reuniones.py`.

- `ai_meetings`: `status` pasa a 30 caracteres y a los estados nuevos
  (`processing` → `procesando`, `done` → `lista`, `failed` → `error`); columnas
  de origen, plataforma externa, bot, aviso y consentimiento, idioma, preguntas
  abiertas, retención separada (audio y transcripción), acta y llamada del
  chat (`call_id`, `conversation_id`; cuarta vía, origen `chat_call`).
- `ai_meeting_actions.ticket_id`.
- Tablas nuevas: `ai_meeting_participants`, `ai_meeting_segments`,
  `ai_meeting_translations`, `ai_meeting_audio`, `ai_meeting_events`,
  `ai_meeting_user_prefs` (todas con `organization_id`; la RLS la aplica
  `env.py` tras cada `upgrade`).

Idempotente (columnas y tablas solo si faltan). Las reuniones existentes se
quedan con `origin = transcript` y sin caducidad de transcripción (la pone la
siguiente edición o el análisis): no se borra nada al migrar.

Downgrade: borra las tablas nuevas y las columnas añadidas, y devuelve los
estados a los antiguos (`programada/bot_unido/grabando/esperando_consentimiento`
→ `processing`).

Revision ID: 188_asistente_de_reuniones
Revises: 186_catalogos_de_tipo_sector_y_categoria
"""
import sqlalchemy as sa
from alembic import op

revision = "188_asistente_de_reuniones"
down_revision = "186_catalogos_de_tipo_sector_y_categoria"
branch_labels = None
depends_on = None

_TZ = sa.DateTime(timezone=True)


def _tablas() -> set:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columnas(tabla) -> set:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(tabla)}


#: (nombre, tipo, FK destino o None, ondelete, índice)
_COLUMNAS_REUNION = (
    ("updated_at", _TZ, None, None, False),
    ("origin", sa.String(20), None, None, True),
    ("external_id", sa.String(255), None, None, True),
    ("join_url", sa.String(1000), None, None, False),
    ("client_id", sa.String(36), "clients.id", "SET NULL", True),
    ("calendar_event_id", sa.String(36), "calendar_events.id", "SET NULL", True),
    ("ends_at", _TZ, None, None, False),
    ("original_language", sa.String(10), None, None, False),
    ("open_questions", sa.Text(), None, None, False),
    ("error_code", sa.String(80), None, None, False),
    ("notice_confirmed_by", sa.String(36), "users.id", "SET NULL", True),
    ("notice_confirmed_at", _TZ, None, None, False),
    ("bot_provider", sa.String(30), None, None, False),
    ("bot_id", sa.String(255), None, None, True),
    ("bot_status", sa.String(40), None, None, False),
    ("audio_expires_at", _TZ, None, None, True),
    ("transcript_expires_at", _TZ, None, None, True),
    ("transcript_purged_at", _TZ, None, None, False),
    ("minutes_document_id", sa.String(36), "documents.id", "SET NULL", True),
    # Cuarta vía: llamada del chat interno.
    ("call_id", sa.String(36), "collaboration_calls.id", "SET NULL", True),
    ("conversation_id", sa.String(36), "collaboration_conversations.id", "SET NULL", True),
)

_ESTADOS = (("processing", "procesando"), ("done", "lista"), ("failed", "error"))


def _org():
    return sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=True)


def _reunion():
    return sa.Column("meeting_id", sa.String(36), sa.ForeignKey("ai_meetings.id", ondelete="CASCADE"),
                     nullable=False)


def _usuario(nombre, ondelete="SET NULL", nullable=True):
    return sa.Column(nombre, sa.String(36), sa.ForeignKey("users.id", ondelete=ondelete), nullable=nullable)


def _crear(nombre, *columnas, indices=(), extra=()):
    if nombre in _tablas():
        return
    op.create_table(nombre, sa.Column("id", sa.String(36), primary_key=True), _org(), *columnas, *extra)
    for c in ("organization_id", *indices):
        op.create_index(f"ix_{nombre}_{c}", nombre, [c])


def upgrade() -> None:
    ahora = sa.func.now()
    hay = _columnas("ai_meetings")
    with op.batch_alter_table("ai_meetings") as b:
        b.alter_column("status", type_=sa.String(30), existing_type=sa.String(20), existing_nullable=True)
        for nombre, tipo, fk, ondelete, indice in _COLUMNAS_REUNION:
            if nombre in hay:
                continue
            b.add_column(sa.Column(nombre, tipo, nullable=True))
            if fk:
                b.create_foreign_key(f"fk_ai_meetings_{nombre}", fk.split(".")[0], [nombre], ["id"],
                                     ondelete=ondelete)
            if indice:
                b.create_index(f"ix_ai_meetings_{nombre}", [nombre])
        if "consent_required" not in hay:
            b.add_column(sa.Column("consent_required", sa.Boolean(), nullable=False, server_default=sa.false()))
    if "ticket_id" not in _columnas("ai_meeting_actions"):
        with op.batch_alter_table("ai_meeting_actions") as b:
            b.add_column(sa.Column("ticket_id", sa.String(36), nullable=True))
            b.create_foreign_key("fk_ai_meeting_actions_ticket_id", "sd_tickets", ["ticket_id"], ["id"],
                                 ondelete="SET NULL")
            b.create_index("ix_ai_meeting_actions_ticket_id", ["ticket_id"])

    reuniones = sa.table("ai_meetings", sa.column("status", sa.String), sa.column("origin", sa.String))
    for antes, despues in _ESTADOS:
        op.execute(reuniones.update().where(reuniones.c.status == antes).values(status=despues))
    op.execute(reuniones.update().where(reuniones.c.origin.is_(None)).values(origin="transcript"))

    _crear("ai_meeting_participants", _reunion(), _usuario("user_id"),
           sa.Column("name", sa.String(255), nullable=True),
           sa.Column("email", sa.String(255), nullable=True),
           sa.Column("role", sa.String(20), nullable=False, server_default="asistente"),
           sa.Column("consent", sa.Boolean(), nullable=True),
           sa.Column("consent_method", sa.String(20), nullable=True),
           sa.Column("consent_at", _TZ, nullable=True),
           _usuario("consent_by"),
           sa.Column("language", sa.String(10), nullable=True),
           sa.Column("created_at", _TZ, server_default=ahora, nullable=True),
           indices=("meeting_id", "user_id", "email", "consent_by"))
    _crear("ai_meeting_segments", _reunion(),
           sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
           sa.Column("speaker", sa.String(255), nullable=True),
           sa.Column("participant_id", sa.String(36),
                     sa.ForeignKey("ai_meeting_participants.id", ondelete="SET NULL"), nullable=True),
           _usuario("user_id"),
           sa.Column("start_ms", sa.Integer(), nullable=True),
           sa.Column("end_ms", sa.Integer(), nullable=True),
           sa.Column("text", sa.Text(), nullable=False),
           sa.Column("language", sa.String(10), nullable=True),
           sa.Column("created_at", _TZ, server_default=ahora, nullable=True),
           indices=("meeting_id", "participant_id", "user_id"))
    if "ix_ai_meeting_segments_meeting_order" not in {i["name"] for i in sa.inspect(op.get_bind())
                                                       .get_indexes("ai_meeting_segments")}:
        op.create_index("ix_ai_meeting_segments_meeting_order", "ai_meeting_segments", ["meeting_id", "orden"])
    _crear("ai_meeting_translations", _reunion(),
           sa.Column("language", sa.String(10), nullable=False),
           sa.Column("contenido", sa.Text(), nullable=False),
           sa.Column("provider", sa.String(30), nullable=True),
           sa.Column("created_at", _TZ, server_default=ahora, nullable=True),
           indices=("meeting_id",),
           extra=(sa.UniqueConstraint("meeting_id", "language", name="uq_ai_meeting_translations_meeting_lang"),))
    _crear("ai_meeting_audio", _reunion(),
           sa.Column("seq", sa.Integer(), nullable=False, server_default="0"),
           sa.Column("storage_key", sa.String(500), nullable=False),
           sa.Column("bytes", sa.Integer(), nullable=False, server_default="0"),
           sa.Column("mime", sa.String(100), nullable=True),
           sa.Column("offset_ms", sa.Integer(), nullable=False, server_default="0"),
           sa.Column("transcribed", sa.Boolean(), nullable=False, server_default=sa.false()),
           sa.Column("stt_provider", sa.String(30), nullable=True),
           sa.Column("expires_at", _TZ, nullable=True),
           sa.Column("created_at", _TZ, server_default=ahora, nullable=True),
           indices=("meeting_id", "expires_at"))
    _crear("ai_meeting_events", _reunion(),
           sa.Column("tipo", sa.String(40), nullable=False),
           _usuario("actor_id"),
           sa.Column("datos", sa.Text(), nullable=True),
           sa.Column("created_at", _TZ, server_default=ahora, nullable=True),
           indices=("meeting_id", "actor_id", "created_at"))
    _crear("ai_meeting_user_prefs", _usuario("user_id", ondelete="CASCADE", nullable=False),
           sa.Column("collect_teams", sa.Boolean(), nullable=False, server_default=sa.false()),
           sa.Column("collect_meet", sa.Boolean(), nullable=False, server_default=sa.false()),
           sa.Column("bot_for_my_calendar", sa.Boolean(), nullable=False, server_default=sa.false()),
           sa.Column("language", sa.String(10), nullable=True),
           sa.Column("updated_at", _TZ, server_default=ahora, nullable=True),
           indices=("user_id",),
           extra=(sa.UniqueConstraint("user_id", name="uq_ai_meeting_user_prefs_user"),))


def downgrade() -> None:
    for t in ("ai_meeting_user_prefs", "ai_meeting_events", "ai_meeting_audio", "ai_meeting_translations",
              "ai_meeting_segments", "ai_meeting_participants"):
        if t in _tablas():
            op.drop_table(t)
    if "ticket_id" in _columnas("ai_meeting_actions"):
        with op.batch_alter_table("ai_meeting_actions") as b:
            b.drop_index("ix_ai_meeting_actions_ticket_id")
            b.drop_constraint("fk_ai_meeting_actions_ticket_id", type_="foreignkey")
            b.drop_column("ticket_id")
    reuniones = sa.table("ai_meetings", sa.column("status", sa.String))
    for antes, despues in _ESTADOS:
        op.execute(reuniones.update().where(reuniones.c.status == despues).values(status=antes))
    op.execute(reuniones.update().where(reuniones.c.status.in_(
        ("programada", "bot_unido", "grabando", "esperando_consentimiento"))).values(status="processing"))
    hay = _columnas("ai_meetings")
    with op.batch_alter_table("ai_meetings") as b:
        for nombre, _tipo, fk, _ondelete, indice in reversed(_COLUMNAS_REUNION):
            if nombre not in hay:
                continue
            if indice:
                b.drop_index(f"ix_ai_meetings_{nombre}")
            if fk:
                b.drop_constraint(f"fk_ai_meetings_{nombre}", type_="foreignkey")
            b.drop_column(nombre)
        if "consent_required" in hay:
            b.drop_column("consent_required")
        b.alter_column("status", type_=sa.String(20), existing_type=sa.String(30), existing_nullable=True)
