"""Políticas de retención generales y bloqueo legal.

Revisión 2026-11 (lo que contecmind y contecintelligence tenían).
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "140_retencion_bloqueo"
down_revision: Union[str, None] = "139_banco_ask_data"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tablas = sa.inspect(op.get_bind()).get_table_names()
    if "retention_policies" not in tablas:
        op.create_table(
            "retention_policies",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=True, index=True),
            sa.Column("entity", sa.String(40), nullable=False),
            sa.Column("keep_days", sa.Integer(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_deleted", sa.Integer(), nullable=True),
            sa.Column("updated_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("uq_retention_policies_org_entity", "retention_policies", ["organization_id", "entity"],
                        unique=True)
    if "legal_holds" not in tablas:
        op.create_table(
            "legal_holds",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=True, index=True),
            sa.Column("case_reference", sa.String(120), nullable=False),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("entity", sa.String(40), nullable=False, server_default="*"),
            sa.Column("field", sa.String(60), nullable=False),
            sa.Column("value", sa.String(255), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("released_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    op.drop_table("legal_holds")
    op.drop_table("retention_policies")
