"""Indices en claves ajenas que se filtran a menudo y no tenian ninguno.

Barrido final 2026-11. De 383 claves ajenas sin indice propio (PostgreSQL no
los crea solo), estas son las que mas aparecen en filtros `Modelo.col ==` de
app/: los tickets del portal por solicitante, los miembros de un grupo de
agentes, las subtareas, los presupuestos de un proyecto, etc. Sin indice, cada
uno es un recorrido secuencial de la tabla y un borrado en cascada del padre
recorre la hija entera.

Mismo patron que la 073: idempotente (IF NOT EXISTS), CONCURRENTLY en
PostgreSQL, nombres `ix_<tabla>_<columna>` iguales a los de `index=True` en los
modelos.
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "163_indices_de_claves_ajenas_calientes"
down_revision: Union[str, None] = "162_perfil_semantico_por_organizacion"
branch_labels = None
depends_on = None

INDICES = [
    ("sd_tickets", "requester_client_id"),
    ("sd_tickets", "created_by_user_id"),
    ("sd_tickets", "ci_id"),
    ("sd_tickets", "problem_id"),
    ("sd_agent_group_members", "group_id"),
    ("client_messages", "parent_id"),
    ("user_skills", "skill_id"),
    ("budgets", "project_id"),
    ("subcontractor_timelogs", "project_id"),
    ("tasks", "parent_task_id"),
    ("approval_steps", "workflow_id"),
    ("rate_entries", "table_id"),
]


def _nombre(tabla: str, columna: str) -> str:
    return f"ix_{tabla}_{columna}"[:63]


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    pg = bind.dialect.name == "postgresql"
    tablas = set(insp.get_table_names())
    with op.get_context().autocommit_block():
        for tabla, columna in INDICES:
            if tabla not in tablas:
                continue
            if columna not in {c["name"] for c in insp.get_columns(tabla)}:
                continue
            nombre = _nombre(tabla, columna)
            if nombre in {i["name"] for i in insp.get_indexes(tabla)}:
                continue
            concurrente = "CONCURRENTLY " if pg else ""
            op.execute(f'CREATE INDEX {concurrente}IF NOT EXISTS "{nombre}" ON "{tabla}" ("{columna}")')


def downgrade() -> None:
    pg = op.get_bind().dialect.name == "postgresql"
    with op.get_context().autocommit_block():
        for tabla, columna in INDICES:
            concurrente = "CONCURRENTLY " if pg else ""
            op.execute(f'DROP INDEX {concurrente}IF EXISTS "{_nombre(tabla, columna)}"')
