"""Obligaciones ASC 606: metodo, precio de venta independiente y notas.

Auditoria 2026-11: la pantalla de ingresos mandaba `method`, `standalone_price`
y `notes` al crear una obligacion de desempeno y el modelo no los tenia, asi que
el alta respondia 500. ASC 606 / IFRS 15 reparte el precio del contrato entre
las obligaciones en proporcion a su precio de venta independiente (paso 4), de
modo que el dato es del dominio y se guarda.
"""
import sqlalchemy as sa
from alembic import op

revision = "158_obligaciones_asc606_precio_y_metodo"
down_revision = "157_mfa_intentos_y_reuso"
branch_labels = None
depends_on = None


def _columnas(tabla: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(tabla)}


def upgrade() -> None:
    existentes = _columnas("rev_obligations")
    with op.batch_alter_table("rev_obligations") as lote:
        if "method" not in existentes:
            lote.add_column(sa.Column("method", sa.String(32), nullable=True))
        if "standalone_price" not in existentes:
            lote.add_column(sa.Column("standalone_price", sa.Float(), nullable=True))
        if "notes" not in existentes:
            lote.add_column(sa.Column("notes", sa.Text(), nullable=True))


def downgrade() -> None:
    existentes = _columnas("rev_obligations")
    with op.batch_alter_table("rev_obligations") as lote:
        for columna in ("notes", "standalone_price", "method"):
            if columna in existentes:
                lote.drop_column(columna)
