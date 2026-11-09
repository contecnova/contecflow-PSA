"""Lecciones aprendidas: lecciones, usos de cada recomendación y acciones de mejora.

Revisión 2026-11. Ver app/models/lecciones.py.
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "142_lecciones_aprendidas"
down_revision: Union[str, None] = "141_conectores_contec"
branch_labels = None
depends_on = None


def _org():
    return sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                     nullable=True, index=True)


def _usuario(nombre: str, index: bool = False):
    return sa.Column(nombre, sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=index)


def upgrade() -> None:
    tablas = sa.inspect(op.get_bind()).get_table_names()
    if "lecciones" not in tablas:
        op.create_table(
            "lecciones",
            sa.Column("id", sa.String(36), primary_key=True),
            _org(),
            sa.Column("codigo", sa.String(20), nullable=False),
            sa.Column("titulo", sa.String(300), nullable=False),
            sa.Column("tipo", sa.String(10), nullable=False, server_default="evitar"),
            sa.Column("categoria", sa.String(40), nullable=False),
            sa.Column("severidad", sa.String(10), nullable=False, server_default="media"),
            sa.Column("que_paso", sa.Text(), nullable=False),
            sa.Column("causa", sa.Text(), nullable=True),
            sa.Column("impacto", sa.Text(), nullable=True),
            sa.Column("recomendacion", sa.Text(), nullable=False),
            sa.Column("estado", sa.String(15), nullable=False, server_default="borrador", index=True),
            sa.Column("origen_tipo", sa.String(20), nullable=False, server_default="manual"),
            sa.Column("origen_id", sa.String(64), nullable=True),
            sa.Column("origen_ref", sa.String(120), nullable=True),
            sa.Column("hechos", sa.Text(), nullable=True),
            sa.Column("proyecto_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True,
                      index=True),
            sa.Column("cliente_id", sa.String(36), sa.ForeignKey("clients.id", ondelete="SET NULL"), nullable=True,
                      index=True),
            sa.Column("tipo_proyecto", sa.String(30), nullable=True),
            sa.Column("etiquetas", sa.String(500), nullable=True),
            sa.Column("servicio_id", sa.String(36), nullable=True),
            sa.Column("ci_id", sa.String(36), nullable=True),
            sa.Column("vector", sa.Text(), nullable=True),
            _usuario("autor_id"),
            _usuario("validada_por"),
            sa.Column("validada_en", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("uq_lecciones_org_codigo", "lecciones", ["organization_id", "codigo"], unique=True)
        op.create_index("ix_lecciones_origen", "lecciones", ["origen_tipo", "origen_id"])
    if "leccion_usos" not in tablas:
        op.create_table(
            "leccion_usos",
            sa.Column("id", sa.String(36), primary_key=True),
            _org(),
            sa.Column("leccion_id", sa.String(36), sa.ForeignKey("lecciones.id", ondelete="CASCADE"), nullable=False,
                      index=True),
            sa.Column("contexto_tipo", sa.String(20), nullable=False),
            sa.Column("contexto_id", sa.String(64), nullable=True),
            sa.Column("valor", sa.String(12), nullable=False),
            sa.Column("nota", sa.String(500), nullable=True),
            _usuario("user_id"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_leccion_usos_contexto", "leccion_usos", ["contexto_tipo", "contexto_id"])
    if "leccion_acciones" not in tablas:
        op.create_table(
            "leccion_acciones",
            sa.Column("id", sa.String(36), primary_key=True),
            _org(),
            sa.Column("leccion_id", sa.String(36), sa.ForeignKey("lecciones.id", ondelete="CASCADE"), nullable=False,
                      index=True),
            sa.Column("descripcion", sa.Text(), nullable=False),
            _usuario("responsable_id", index=True),
            sa.Column("fecha_limite", sa.Date(), nullable=True),
            sa.Column("estado", sa.String(12), nullable=False, server_default="abierta", index=True),
            sa.Column("resultado", sa.Text(), nullable=True),
            sa.Column("cerrada_en", sa.DateTime(timezone=True), nullable=True),
            _usuario("created_by"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )


def downgrade() -> None:
    op.drop_table("leccion_acciones")
    op.drop_table("leccion_usos")
    op.drop_table("lecciones")
