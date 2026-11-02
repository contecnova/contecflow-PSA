"""Numeracion por organizacion.

Medido el 2026-11-02 con dos organizaciones:

- `numbering_sequences.entity` era unico en toda la base. En cuanto una
  organizacion tenia su secuencia, la segunda no podia crear la suya y
  `next_numbered_code` reventaba con RuntimeError: sin proyectos, tareas,
  contratos, facturas, cambios ni incidencias mayores para ella.
- `number` de tickets, problemas, articulos e incidencias mayores era unico en
  toda la base, pero cada organizacion numera desde su maximo: la segunda
  chocaba con la primera en cuanto coincidia un numero.

Ahora las dos cosas son unicas por organizacion. Solo PostgreSQL: SQLite no
tiene ALTER de restricciones, y alli el esquema sigue saliendo de la cadena
como hasta ahora (igual que la 097).
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "100_numeracion_por_organizacion"
down_revision: Union[str, None] = "099_politica_sla_con_calendario"
branch_labels = None
depends_on = None

# (tabla, columna, restriccion nueva, indice no unico que se conserva o None)
CAMBIOS = (
    ("numbering_sequences", "entity", "uq_numbering_sequences_org_entity", None),
    ("sd_tickets", "number", "uq_sd_tickets_org_number", "ix_sd_tickets_number"),
    ("sd_problems", "number", "uq_sd_problems_org_number", None),
    ("sd_kb_articles", "number", "uq_sd_kb_articles_org_number", None),
    ("sd_major_incidents", "number", "uq_sd_major_incidents_org_number", None),
)


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return
    tablas = set(sa.inspect(conn).get_table_names())
    for tabla, columna, nueva, indice in CAMBIOS:
        if tabla not in tablas:
            continue
        insp = sa.inspect(conn)
        if any(uc["name"] == nueva for uc in insp.get_unique_constraints(tabla)):
            continue
        for uc in insp.get_unique_constraints(tabla):
            if uc["column_names"] == [columna]:
                op.drop_constraint(uc["name"], tabla, type_="unique")
        for ix in insp.get_indexes(tabla):
            if ix.get("unique") and ix["column_names"] == [columna]:
                op.drop_index(ix["name"], table_name=tabla)
        op.create_unique_constraint(nueva, tabla, ["organization_id", columna])
        if indice:
            op.execute(f'CREATE INDEX IF NOT EXISTS "{indice}" ON "{tabla}" ("{columna}")')


def downgrade() -> None:
    # Volver a la unicidad global reintroduce el fallo: la segunda organizacion
    # no podria numerar.
    pass
