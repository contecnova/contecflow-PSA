"""👍/👎 de las respuestas de IA (asistente y portal).

Revisión 2026-11 (lo que contecmind tenía): un 👎 abre una «pregunta sin
respuesta» en la base de conocimiento.
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "136_valoracion_respuestas"
down_revision: Union[str, None] = "135_filas_sin_empresa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "ai_answer_feedback" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "ai_answer_feedback",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=True, index=True),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("message_id", sa.String(36), nullable=False),
        sa.Column("question", sa.Text(), nullable=True),
        sa.Column("helpful", sa.Boolean(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("client_user_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("uq_ai_answer_feedback_org_msg", "ai_answer_feedback",
                    ["organization_id", "channel", "message_id"], unique=True)


def downgrade() -> None:
    op.drop_table("ai_answer_feedback")
