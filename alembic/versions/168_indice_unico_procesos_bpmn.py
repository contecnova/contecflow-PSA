"""Indices unicos de la clave de `bpmn_processes` (por organizacion y global).

Segunda auditoria 2026-11 (#33).

`clave_unica` comprueba en codigo que la clave este libre, pero dos altas
simultaneas pueden pasar la comprobacion a la vez y duplicarla. Esta revision
lo impide en la base con dos indices unicos:
  · `uq_bpmn_processes_org_key` sobre `(organization_id, key)`;
  · `uq_bpmn_processes_key_global` sobre `(key)` donde `organization_id IS NULL`.
    NULL no choca con NULL (PostgreSQL y SQLite), asi que el primero no cubre el
    catalogo global. Indice parcial en los dos motores (como la 091).

Duplicados previos. Antes de crear los indices se buscan los grupos
`(organization_id, key)` con mas de una fila (los NULL se agrupan como un solo
espacio, el del catalogo global). Se resuelve de forma determinista y sin
perder datos: se conserva la clave de la fila **mas antigua** (`created_at`,
desempate por `id`) porque es a la que apuntan referencias externas y la
semilla; a las demas se les anade el sufijo `_dup_<n>` (n = 1, 2... por orden
de antiguedad), y si ese nombre ya existe se sigue con el siguiente n libre.
Ninguna fila se borra ni se desactiva. El sufijo no se revierte en el
downgrade: no se puede saber que claves lo llevaban por un duplicado real.

Mismo patron que la 163 y la 164: idempotente (`IF NOT EXISTS`, se salta si la
tabla no existe), CONCURRENTLY en PostgreSQL. El downgrade quita los indices.
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "168_indice_unico_procesos_bpmn"
down_revision: Union[str, None] = "167_ausencias_reglas_turnos_y_documentos"
branch_labels = None
depends_on = None

TABLA = "bpmn_processes"
IDX_ORG = "uq_bpmn_processes_org_key"
IDX_GLOBAL = "uq_bpmn_processes_key_global"


def _resolver_duplicados(bind) -> int:
    filas = bind.execute(sa.text(
        "SELECT id, organization_id, key FROM bpmn_processes "
        "ORDER BY created_at, id")).fetchall()
    ocupadas = {(f.organization_id, f.key) for f in filas}
    vistas: set = set()
    renombradas = 0
    for f in filas:
        espacio = (f.organization_id, f.key)
        if espacio not in vistas:
            vistas.add(espacio)
            continue
        n = 1
        while (f.organization_id, f"{f.key}_dup_{n}"[:120]) in ocupadas:
            n += 1
        nueva = f"{f.key}_dup_{n}"[:120]
        ocupadas.add((f.organization_id, nueva))
        bind.execute(sa.text("UPDATE bpmn_processes SET key = :k WHERE id = :i"),
                     {"k": nueva, "i": f.id})
        renombradas += 1
    return renombradas


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if TABLA not in insp.get_table_names():
        return
    _resolver_duplicados(bind)
    pg = bind.dialect.name == "postgresql"
    concurrente = "CONCURRENTLY " if pg else ""
    with op.get_context().autocommit_block():
        op.execute(f'CREATE UNIQUE INDEX {concurrente}IF NOT EXISTS "{IDX_ORG}" '
                   f'ON "{TABLA}" ("organization_id", "key")')
        op.execute(f'CREATE UNIQUE INDEX {concurrente}IF NOT EXISTS "{IDX_GLOBAL}" '
                   f'ON "{TABLA}" ("key") WHERE organization_id IS NULL')


def downgrade() -> None:
    pg = op.get_bind().dialect.name == "postgresql"
    concurrente = "CONCURRENTLY " if pg else ""
    with op.get_context().autocommit_block():
        op.execute(f'DROP INDEX {concurrente}IF EXISTS "{IDX_GLOBAL}"')
        op.execute(f'DROP INDEX {concurrente}IF EXISTS "{IDX_ORG}"')
