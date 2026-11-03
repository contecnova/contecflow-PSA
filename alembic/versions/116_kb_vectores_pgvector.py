"""Vectores de la base de conocimiento en pgvector, si el Postgres lo tiene.

Auditoria 2026-11: la busqueda por vectores comparaba en Python contra todos
los articulos. Si la extension `vector` esta disponible, se crea la columna
`sd_kb_articles.embedding_vec` y se rellena con los vectores guardados; si no
(la imagen `postgres:16-alpine` no la trae), no se hace nada y la busqueda
sigue en Python. Ver app/services/service_desk/kb_vectores.py.
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "116_kb_vectores_pgvector"
down_revision: Union[str, None] = "115_uc_plazo_de_respuesta"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.services.service_desk.kb_vectores import preparar
    preparar(op.get_bind())


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql" and any(
            c["name"] == "embedding_vec" for c in sa.inspect(bind).get_columns("sd_kb_articles")):
        op.drop_column("sd_kb_articles", "embedding_vec")
