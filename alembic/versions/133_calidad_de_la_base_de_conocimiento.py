"""Calidad de la base de conocimiento: correcciones, preguntas sin respuesta y avisos.

Revisión 2026-11 (lo que contecmind ya tenía): la respuesta que deja un experto
se aplica a las preguntas parecidas; las preguntas sin artículo forman una lista
de trabajo; y una pasada diaria avisa de artículos caducados y contradictorios.
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "133_calidad_kb"
down_revision: Union[str, None] = "132_reglas_programadas"
branch_labels = None
depends_on = None


def _existe(nombre: str) -> bool:
    return nombre in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _existe("sd_kb_corrections"):
        op.create_table(
            "sd_kb_corrections",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=True, index=True),
            sa.Column("question", sa.Text(), nullable=False),
            sa.Column("answer", sa.Text(), nullable=False),
            sa.Column("question_vec", sa.Text(), nullable=True),
            sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("status", sa.String(20), nullable=False, server_default="active", index=True),
            sa.Column("article_id", sa.String(36), sa.ForeignKey("sd_kb_articles.id", ondelete="SET NULL"), nullable=True),
            sa.Column("gap_id", sa.String(36), nullable=True),
            sa.Column("usage_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    if not _existe("sd_kb_gaps"):
        op.create_table(
            "sd_kb_gaps",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=True, index=True),
            sa.Column("question_key", sa.String(255), nullable=False),
            sa.Column("question", sa.Text(), nullable=False),
            sa.Column("source", sa.String(30), nullable=False),
            sa.Column("times_asked", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("status", sa.String(20), nullable=False, server_default="open", index=True),
            sa.Column("article_id", sa.String(36), sa.ForeignKey("sd_kb_articles.id", ondelete="SET NULL"), nullable=True),
            sa.Column("correction_id", sa.String(36), sa.ForeignKey("sd_kb_corrections.id", ondelete="SET NULL"), nullable=True),
            sa.Column("first_asked_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("last_asked_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("closed_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        )
        op.create_index("uq_sd_kb_gaps_org_key", "sd_kb_gaps", ["organization_id", "question_key"], unique=True)
    if not _existe("sd_kb_findings"):
        op.create_table(
            "sd_kb_findings",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=True, index=True),
            sa.Column("kind", sa.String(20), nullable=False, index=True),
            sa.Column("article_id", sa.String(36), sa.ForeignKey("sd_kb_articles.id", ondelete="CASCADE"), nullable=False),
            sa.Column("other_article_id", sa.String(36), sa.ForeignKey("sd_kb_articles.id", ondelete="CASCADE"), nullable=True),
            sa.Column("detail", sa.Text(), nullable=True),
            sa.Column("score", sa.Float(), nullable=True),
            sa.Column("dedupe_key", sa.String(255), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="open", index=True),
            sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("closed_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        )
        op.create_index("uq_sd_kb_findings_org_key", "sd_kb_findings", ["organization_id", "dedupe_key"], unique=True)


def downgrade() -> None:
    for t in ("sd_kb_findings", "sd_kb_gaps", "sd_kb_corrections"):
        if _existe(t):
            op.drop_table(t)
