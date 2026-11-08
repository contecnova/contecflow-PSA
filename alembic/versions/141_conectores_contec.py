"""Conectores con contecmind y contecintelligence: llamadas, enlaces y carpetas.

Revisión 2026-11. Ver app/models/conectores.py.
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "141_conectores_contec"
down_revision: Union[str, None] = "140_retencion_bloqueo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tablas = sa.inspect(op.get_bind()).get_table_names()
    if "conector_llamadas" not in tablas:
        op.create_table(
            "conector_llamadas",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                      nullable=True, index=True),
            sa.Column("producto", sa.String(40), nullable=False),
            sa.Column("operacion", sa.String(60), nullable=False),
            sa.Column("ok", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("estado_http", sa.Integer(), nullable=True),
            sa.Column("ms", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("error", sa.String(500), nullable=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_conector_llamadas_producto_fecha", "conector_llamadas", ["producto", "created_at"])
    if "enlaces_documentales" not in tablas:
        op.create_table(
            "enlaces_documentales",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                      nullable=True, index=True),
            sa.Column("entidad", sa.String(40), nullable=False),
            sa.Column("entidad_id", sa.String(64), nullable=False),
            sa.Column("document_id", sa.String(64), nullable=False),
            sa.Column("titulo", sa.String(500), nullable=False),
            sa.Column("mime_type", sa.String(120), nullable=True),
            sa.Column("tamano", sa.Integer(), nullable=True),
            sa.Column("origen", sa.String(20), nullable=False, server_default="enlazado"),
            sa.Column("nota", sa.String(500), nullable=True),
            sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("uq_enlaces_documentales", "enlaces_documentales",
                        ["organization_id", "entidad", "entidad_id", "document_id"], unique=True)
        op.create_index("ix_enlaces_documentales_ficha", "enlaces_documentales", ["entidad", "entidad_id"])
    if "carpetas_documentales" not in tablas:
        op.create_table(
            "carpetas_documentales",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                      nullable=True, index=True),
            sa.Column("entidad", sa.String(40), nullable=False),
            sa.Column("entidad_id", sa.String(64), nullable=False),
            sa.Column("folder_id", sa.String(64), nullable=False),
            sa.Column("area_id", sa.String(64), nullable=False),
            sa.Column("ruta", sa.String(1000), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("uq_carpetas_documentales", "carpetas_documentales",
                        ["organization_id", "entidad", "entidad_id"], unique=True)


def downgrade() -> None:
    op.drop_table("carpetas_documentales")
    op.drop_table("enlaces_documentales")
    op.drop_table("conector_llamadas")
