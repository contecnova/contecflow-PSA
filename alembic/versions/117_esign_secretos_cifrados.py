"""Cifra los secretos de e-firma que ya estaban guardados en claro.

Auditoria 2026-11: `app_settings` guardaba en claro las credenciales de
DocuSign y Adobe Sign (`esign.*`). Desde ahora `esign_service` las cifra al
guardar; esta migracion cifra las existentes. Solo datos: no cambia el esquema.
Se descifra con la SECRET_KEY del despliegue (o SECRET_KEY_PREVIOUS).
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "117_esign_secretos_cifrados"
down_revision: Union[str, None] = "116_kb_vectores_pgvector"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.services.esign_service import cifrar_si_es_secreto
    bind = op.get_bind()
    filas = bind.execute(sa.text(
        "SELECT id, key, value FROM app_settings WHERE key LIKE 'esign.%' AND value IS NOT NULL")).all()
    for ident, clave, valor in filas:
        nuevo = cifrar_si_es_secreto(clave, valor)
        if nuevo != valor:
            bind.execute(sa.text("UPDATE app_settings SET value = :v WHERE id = :i"), {"v": nuevo, "i": ident})


def downgrade() -> None:
    # Descifrar para volver a guardar en claro no tiene sentido: no se deshace.
    pass
