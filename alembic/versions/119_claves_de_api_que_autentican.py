"""Huella SHA-256 de las claves de API, para autenticar con ellas.

Auditoria 2026-11: las claves de API no autenticaban nada. Ahora valen en toda
la API (`X-API-Key`), y buscarlas con bcrypt en cada peticion costaria ~0,2 s:
se guarda tambien su SHA-256. Las claves existentes la reciben la primera vez
que se usan (bcrypt por prefijo, una sola vez).

Los tokens del portal ya existentes (PBKDF2 con sal) no se podian buscar y no
han funcionado nunca: caducan solos (1 h) y no se migran.
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "119_claves_de_api_que_autentican"
down_revision: Union[str, None] = "118_automatizaciones_que_disparan"
branch_labels = None
depends_on = None


def upgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("api_keys")}
    if "key_digest" not in cols:
        with op.batch_alter_table("api_keys") as batch:
            batch.add_column(sa.Column("key_digest", sa.String(64), nullable=True))
            batch.create_index("ix_api_keys_key_digest", ["key_digest"], unique=True)


def downgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("api_keys")}
    if "key_digest" in cols:
        with op.batch_alter_table("api_keys") as batch:
            batch.drop_index("ix_api_keys_key_digest")
            batch.drop_column("key_digest")
