"""Base de conocimiento: revision antes de publicar, desvio y vector guardado.

- `kbstatus` gana `in_review`: con revision obligatoria, el autor envia y un
  revisor publica.
- `sd_kb_articles.deflection_count`: veces que un articulo evito un ticket.
- `sd_kb_articles.embedding`: el vector se guarda al guardar el articulo; antes
  la sugerencia al agente recalculaba el de todos en cada peticion.
- `sd_kb_articles.review_comment`: lo que dijo el revisor al devolverlo.
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "105_base_de_conocimiento"
down_revision: Union[str, None] = "104_alertas_de_monitorizacion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE kbstatus ADD VALUE IF NOT EXISTS 'in_review'")
    cols = {c["name"] for c in sa.inspect(conn).get_columns("sd_kb_articles")}
    with op.batch_alter_table("sd_kb_articles") as batch:
        if "deflection_count" not in cols:
            batch.add_column(sa.Column("deflection_count", sa.Integer(), nullable=False, server_default="0"))
        if "embedding" not in cols:
            batch.add_column(sa.Column("embedding", sa.Text(), nullable=True))
        if "review_comment" not in cols:
            batch.add_column(sa.Column("review_comment", sa.Text(), nullable=True))


def downgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("sd_kb_articles")}
    with op.batch_alter_table("sd_kb_articles") as batch:
        for c in ("review_comment", "embedding", "deflection_count"):
            if c in cols:
                batch.drop_column(c)
