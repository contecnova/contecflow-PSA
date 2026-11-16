"""Traduccion en tiempo real operador <-> cliente (16-11-2026).

Tablas nuevas (modelos en `app/models/traduccion.py`):

- `translation_cache`: cada texto traducido una vez por empresa, por
  (texto, origen, destino, glosario); la clave es un SHA-256.
- `message_translations`: traducciones de cada mensaje (comentarios, tickets,
  mensajes de canales y del chat interno) por idioma destino, con su origen
  (auto | author), proveedor, autor y fecha.
- `translation_glossary_terms`: glosario de la empresa.
- `sd_kb_article_translations`: versiones de los articulos de la base de
  conocimiento en los idiomas del portal, con revision.

Columnas nuevas:

- `sd_tickets.language`, `sd_tickets.system_template`, `sd_tickets.system_params`.
- `sd_ticket_comments.language`.
- `sd_channel_messages.language`.

Datos: ninguno. El idioma de los mensajes existentes queda vacio y se rellena
la primera vez que se traducen (el proveedor lo detecta).

Revision ID: 175_traduccion_en_tiempo_real
Revises: 174_service_desk_mercado
"""
import sqlalchemy as sa
from alembic import op

revision = "175_traduccion_en_tiempo_real"
down_revision = "174_service_desk_mercado"
branch_labels = None
depends_on = None


def _tablas(con) -> set[str]:
    return set(sa.inspect(con).get_table_names())


def _columnas(con, tabla: str) -> set[str]:
    return {c["name"] for c in sa.inspect(con).get_columns(tabla)}


def _org():
    return sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                     nullable=True)


def upgrade() -> None:
    con = op.get_bind()
    tablas = _tablas(con)

    if "translation_cache" not in tablas:
        op.create_table(
            "translation_cache",
            sa.Column("id", sa.String(36), primary_key=True),
            _org(),
            sa.Column("cache_key", sa.String(64), nullable=False),
            sa.Column("source_language", sa.String(16), nullable=True),
            sa.Column("target_language", sa.String(16), nullable=False),
            sa.Column("translated_text", sa.Text(), nullable=False),
            sa.Column("provider", sa.String(30), nullable=False),
            sa.Column("characters", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("hits", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("organization_id", "cache_key", name="uq_translation_cache_org_key"),
        )
        op.create_index("ix_translation_cache_organization_id", "translation_cache", ["organization_id"])
        op.create_index("ix_translation_cache_last_used_at", "translation_cache", ["last_used_at"])

    if "message_translations" not in tablas:
        op.create_table(
            "message_translations",
            sa.Column("id", sa.String(36), primary_key=True),
            _org(),
            sa.Column("message_type", sa.String(30), nullable=False),
            sa.Column("message_id", sa.String(36), nullable=False),
            sa.Column("field", sa.String(30), nullable=False, server_default="body"),
            sa.Column("source_language", sa.String(16), nullable=True),
            sa.Column("target_language", sa.String(16), nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("origin", sa.String(10), nullable=False, server_default="auto"),
            sa.Column("provider", sa.String(30), nullable=True),
            sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"),
                      nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("organization_id", "message_type", "message_id", "field", "target_language",
                                name="uq_message_translation"),
        )
        op.create_index("ix_message_translations_organization_id", "message_translations", ["organization_id"])
        op.create_index("ix_message_translations_message_id", "message_translations", ["message_id"])

    if "translation_glossary_terms" not in tablas:
        op.create_table(
            "translation_glossary_terms",
            sa.Column("id", sa.String(36), primary_key=True),
            _org(),
            sa.Column("term", sa.String(200), nullable=False),
            sa.Column("translations", sa.Text(), nullable=True),
            sa.Column("case_sensitive", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("notes", sa.String(500), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"),
                      nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("organization_id", "term", name="uq_translation_glossary_org_term"),
        )
        op.create_index("ix_translation_glossary_terms_organization_id", "translation_glossary_terms",
                        ["organization_id"])

    if "sd_kb_article_translations" not in tablas:
        op.create_table(
            "sd_kb_article_translations",
            sa.Column("id", sa.String(36), primary_key=True),
            _org(),
            sa.Column("article_id", sa.String(36), sa.ForeignKey("sd_kb_articles.id", ondelete="CASCADE"),
                      nullable=False),
            sa.Column("language", sa.String(16), nullable=False),
            sa.Column("title", sa.String(500), nullable=False),
            sa.Column("summary", sa.String(500), nullable=True),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("status", sa.String(12), nullable=False, server_default="draft"),
            sa.Column("provider", sa.String(30), nullable=True),
            sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("generated_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"),
                      nullable=True),
            sa.Column("reviewed_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"),
                      nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("review_comment", sa.String(500), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("article_id", "language", name="uq_sd_kb_article_translation_lang"),
        )
        op.create_index("ix_sd_kb_article_translations_organization_id", "sd_kb_article_translations",
                        ["organization_id"])
        op.create_index("ix_sd_kb_article_translations_article_id", "sd_kb_article_translations", ["article_id"])
        op.create_index("ix_sd_kb_article_translations_status", "sd_kb_article_translations", ["status"])

    cols = _columnas(con, "sd_tickets")
    with op.batch_alter_table("sd_tickets") as t:
        if "language" not in cols:
            t.add_column(sa.Column("language", sa.String(16), nullable=True))
        if "system_template" not in cols:
            t.add_column(sa.Column("system_template", sa.String(60), nullable=True))
        if "system_params" not in cols:
            t.add_column(sa.Column("system_params", sa.Text(), nullable=True))
    if "language" not in _columnas(con, "sd_ticket_comments"):
        with op.batch_alter_table("sd_ticket_comments") as t:
            t.add_column(sa.Column("language", sa.String(16), nullable=True))
    if "language" not in _columnas(con, "sd_channel_messages"):
        with op.batch_alter_table("sd_channel_messages") as t:
            t.add_column(sa.Column("language", sa.String(16), nullable=True))


def downgrade() -> None:
    con = op.get_bind()
    with op.batch_alter_table("sd_channel_messages") as t:
        t.drop_column("language")
    with op.batch_alter_table("sd_ticket_comments") as t:
        t.drop_column("language")
    with op.batch_alter_table("sd_tickets") as t:
        t.drop_column("system_params")
        t.drop_column("system_template")
        t.drop_column("language")
    con.execute(sa.text("DELETE FROM app_settings WHERE key LIKE 'TRANSLATION\\_%' ESCAPE '\\'"))
    con.execute(sa.text("DELETE FROM integration_credentials WHERE provider IN ('deepl', 'azure_translator')"))
    for tabla in ("sd_kb_article_translations", "translation_glossary_terms", "message_translations",
                  "translation_cache"):
        op.drop_table(tabla)
