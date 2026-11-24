"""Certificaciones: `cert_correspondencias.id_semilla` (24-11-2026, docs/CERTIFICACIONES.md §Biblioteca).

La importación del texto oficial con licencia puede corregir el identificador de
un control (ids de referencia de TISAX ISA 6 y de 62443-4-2 por tipo de
componente). `id_semilla` guarda el que trae el contenido común para que la
sincronización no lo vuelva a crear y no se pierda el enlace al control.

La 212 ya la trae en una instalación nueva; una base a la que se aplicó la 212
antes de añadirla (la real, 24-11-2026) la recibe aquí. Idempotente (mira la
columna), SQLite y Postgres (`batch_alter_table`). Deshacer real: quita la
columna (los ids corregidos se quedan en `id_control`).

Revision ID: 213_certificaciones_id_semilla
Revises: 212_certificaciones
"""
import sqlalchemy as sa
from alembic import op

revision = "213_certificaciones_id_semilla"
down_revision = "212_certificaciones"
branch_labels = None
depends_on = None

TABLA = "cert_correspondencias"


def _cols() -> set:
    insp = sa.inspect(op.get_bind())
    if TABLA not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(TABLA)}


def upgrade() -> None:
    cols = _cols()
    if cols and "id_semilla" not in cols:
        with op.batch_alter_table(TABLA) as b:
            b.add_column(sa.Column("id_semilla", sa.String(60), nullable=True))
    if cols:
        # Las filas sembradas antes de la columna: su id es el de la semilla.
        op.execute(sa.text(f"UPDATE {TABLA} SET id_semilla = id_control WHERE id_semilla IS NULL AND sembrado = :s")
                   .bindparams(s=True))


def downgrade() -> None:
    if "id_semilla" in _cols():
        with op.batch_alter_table(TABLA) as b:
            b.drop_column("id_semilla")
