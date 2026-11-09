"""Gastos: varios justificantes, reparto entre proyectos, políticas y kilometraje.

Revisión 2026-11. Ver app/models/expenses.py.
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "143_gastos_avanzados"
down_revision: Union[str, None] = "142_lecciones_aprendidas"
branch_labels = None
depends_on = None


def _org():
    return sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                     nullable=True, index=True)


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    tablas = insp.get_table_names()
    columnas = {c["name"] for c in insp.get_columns("expenses")}
    with op.batch_alter_table("expenses") as t:
        if "km" not in columnas:
            t.add_column(sa.Column("km", sa.Float(), nullable=True))
        if "policy_flags" not in columnas:
            t.add_column(sa.Column("policy_flags", sa.Text(), nullable=True))
    if "expense_attachments" not in tablas:
        op.create_table(
            "expense_attachments",
            sa.Column("id", sa.String(36), primary_key=True),
            _org(),
            sa.Column("expense_id", sa.String(36), sa.ForeignKey("expenses.id", ondelete="CASCADE"), nullable=False,
                      index=True),
            sa.Column("filename", sa.String(255), nullable=False),
            sa.Column("content_type", sa.String(120), nullable=True),
            sa.Column("size_bytes", sa.Integer(), nullable=True),
            sa.Column("storage_key", sa.String(500), nullable=False),
            sa.Column("uploaded_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    if "expense_allocations" not in tablas:
        op.create_table(
            "expense_allocations",
            sa.Column("id", sa.String(36), primary_key=True),
            _org(),
            sa.Column("expense_id", sa.String(36), sa.ForeignKey("expenses.id", ondelete="CASCADE"), nullable=False,
                      index=True),
            sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False,
                      index=True),
            sa.Column("percentage", sa.Float(), nullable=False),
        )
    if "expense_policies" not in tablas:
        op.create_table(
            "expense_policies",
            sa.Column("id", sa.String(36), primary_key=True),
            _org(),
            sa.Column("nombre", sa.String(200), nullable=False),
            sa.Column("categoria", sa.String(30), nullable=True),
            sa.Column("limite_por_gasto", sa.Float(), nullable=True),
            sa.Column("limite_diario", sa.Float(), nullable=True),
            sa.Column("justificante_desde", sa.Float(), nullable=True),
            sa.Column("justificacion_desde", sa.Float(), nullable=True),
            sa.Column("accion", sa.String(10), nullable=False, server_default="bloquear"),
            sa.Column("activa", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )


def downgrade() -> None:
    op.drop_table("expense_policies")
    op.drop_table("expense_allocations")
    op.drop_table("expense_attachments")
    with op.batch_alter_table("expenses") as t:
        t.drop_column("policy_flags")
        t.drop_column("km")
