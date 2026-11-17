"""Versiones revisables de avisos y catalogo en los idiomas del portal (17-11-2026).

Tabla nueva (modelo `PortalContentTranslation` en `app/models/traduccion.py`):

- `portal_content_translations`: la version de un aviso (`announcement`) o del
  nombre y la descripcion de una categoria o servicio del catalogo
  (`catalog_category`, `catalog_service`) en un idioma del portal, con su
  revision (`draft` -> `in_review` -> `published` | `rejected`) y la huella de
  los textos originales (`source_hash`) para saber si se ha quedado
  desactualizada.

Datos: ninguno. Hasta que se generen versiones, el portal sigue sirviendo la
traduccion automatica en cache, como antes.

Revision ID: 181_versiones_avisos_y_catalogo
Revises: 180_turnos_y_ausencias_por_horas
"""
import sqlalchemy as sa
from alembic import op

revision = "181_versiones_avisos_y_catalogo"
down_revision = "180_turnos_y_ausencias_por_horas"
branch_labels = None
depends_on = None

TABLA = "portal_content_translations"


def upgrade() -> None:
    con = op.get_bind()
    if TABLA in set(sa.inspect(con).get_table_names()):
        return
    op.create_table(
        TABLA,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                  nullable=True),
        sa.Column("content_type", sa.String(30), nullable=False),
        sa.Column("content_id", sa.String(36), nullable=False),
        sa.Column("language", sa.String(16), nullable=False),
        sa.Column("fields", sa.Text(), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="in_review"),
        sa.Column("provider", sa.String(30), nullable=True),
        sa.Column("source_language", sa.String(16), nullable=True),
        sa.Column("source_hash", sa.String(64), nullable=True),
        sa.Column("generated_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("reviewed_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_comment", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("content_type", "content_id", "language", name="uq_portal_content_translation_lang"),
    )
    op.create_index("ix_portal_content_translations_organization_id", TABLA, ["organization_id"])
    op.create_index("ix_portal_content_translations_content_id", TABLA, ["content_id"])
    op.create_index("ix_portal_content_translations_status", TABLA, ["status"])


def downgrade() -> None:
    op.drop_table(TABLA)
