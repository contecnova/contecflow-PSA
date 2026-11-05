"""Banco de preguntas validadas de Ask-the-Data.

Revisión 2026-11 (lo que contecintelligence tenía).
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "139_banco_ask_data"
down_revision: Union[str, None] = "138_reserva_documentos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "ask_data_examples" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "ask_data_examples",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=True, index=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("question_norm", sa.String(500), nullable=False),
        sa.Column("sql", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("times_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("uq_ask_data_examples_org_q", "ask_data_examples", ["organization_id", "question_norm"],
                    unique=True)


def downgrade() -> None:
    op.drop_table("ask_data_examples")
