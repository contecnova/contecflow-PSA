"""Usuarios del portal: archivar en vez de borrar cuando tienen historial (23-11-2026).

Docs: docs/seguridad/politicas_de_cuenta.md §«Portal de clientes: contraseña a mano,
eliminar y archivar».

Columnas nuevas en `client_users`:

- `archived_at` (fecha con zona, nula): el usuario se archivó. Archivado = no
  entra (`is_active=False`), sale de las listas por defecto y conserva todo su
  historial con su nombre. «Restaurar» la vacía.
- `archived_by` (texto 36, nulo): quién lo archivó (id del operador). Sin clave
  ajena a propósito: el rastro completo está en `audit_log` y borrar al operador
  no debe tocar esta fila.

Sin datos que migrar: hasta hoy «Eliminar» borraba de verdad, así que no hay
usuarios archivados. Los suspendidos (`is_active=False`) siguen suspendidos.

Compatible con SQLite y Postgres: `batch_alter_table` (en SQLite, `ADD COLUMN`
directo; el `DROP COLUMN` del deshacer recrea la tabla). Idempotente: mira antes
si cada columna existe.

Deshacer real: borra las dos columnas. Los usuarios que estuvieran archivados
quedan como suspendidos (`is_active=False`), sin perder nada más.

Revision ID: 205_portal_usuarios
Revises: 204_bpm
"""
import sqlalchemy as sa
from alembic import op

revision = "205_portal_usuarios"
down_revision = "204_bpm"
branch_labels = None
depends_on = None

TABLA = "client_users"


def _columnas() -> set:
    insp = sa.inspect(op.get_bind())
    if TABLA not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(TABLA)}


def upgrade() -> None:
    existentes = _columnas()
    if not existentes:
        return
    nuevas = [c for c in ("archived_at", "archived_by") if c not in existentes]
    if not nuevas:
        return
    with op.batch_alter_table(TABLA) as b:
        if "archived_at" in nuevas:
            b.add_column(sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
        if "archived_by" in nuevas:
            b.add_column(sa.Column("archived_by", sa.String(36), nullable=True))


def downgrade() -> None:
    sobran = [c for c in ("archived_by", "archived_at") if c in _columnas()]
    if not sobran:
        return
    with op.batch_alter_table(TABLA) as b:
        for c in sobran:
            b.drop_column(c)
