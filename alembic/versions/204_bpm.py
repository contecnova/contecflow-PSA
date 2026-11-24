"""BPM profesional: asignacion, SLA de tareas, versiones retiradas, llamadas y variables tipadas.

Revision BPM 2026-11-23 (docs/BPM.md).

- `bpmn_processes.variables_schema`: variables declaradas del proceso (tipo,
  obligatoria, dato personal para RGPD).
- `bpmn_process_versions.published_by_user_id`, `retired_at`,
  `retired_by_user_id`: quien publico (segregacion de funciones) y el ciclo
  borrador -> publicada -> retirada.
- `bpmn_instances.business_key`, `parent_instance_id`, `parent_step_id`,
  `suspended_at`: correlacion de mensajes, actividades de llamada y
  suspension.
- `bpmn_instance_steps.assignee_user_id`, `candidate_groups`, `sla_due_at`,
  `escalated_at`, `attempts`: asignacion a persona, rol, grupo o cola; plazo y
  escalado de la tarea; reintentos de las acciones automaticas.

Compatible con SQLite (batch) y PostgreSQL. Idempotente: no anade lo que ya
existe. El downgrade quita todo lo anadido.

Revision ID: 204_bpm
Revises: 203_ticket_a_pr
"""
import sqlalchemy as sa
from alembic import op

revision = "204_bpm"
down_revision = "203_ticket_a_pr"
branch_labels = None
depends_on = None


def _fk(destino: str, tabla: str, columna: str):
    # Con nombre: en `batch_alter_table` (SQLite) una constraint sin nombre falla
    # («Constraint must have a name»).
    return sa.ForeignKey(f"{destino}.id", ondelete="SET NULL", name=f"fk_{tabla}_{columna}"[:60])


#: tabla -> [(columna, tipo, kwargs, indice?)]
COLUMNAS = {
    "bpmn_processes": [
        ("variables_schema", sa.Text(), {}, False),
    ],
    "bpmn_process_versions": [
        ("published_by_user_id", sa.String(36), {"fk": "users"}, True),
        ("retired_at", sa.DateTime(timezone=True), {}, False),
        ("retired_by_user_id", sa.String(36), {"fk": "users"}, True),
    ],
    "bpmn_instances": [
        ("business_key", sa.String(120), {}, True),
        ("parent_instance_id", sa.String(36), {"fk": "bpmn_instances"}, True),
        ("parent_step_id", sa.String(36), {}, False),
        ("suspended_at", sa.DateTime(timezone=True), {}, False),
    ],
    "bpmn_instance_steps": [
        ("assignee_user_id", sa.String(36), {"fk": "users"}, True),
        ("candidate_groups", sa.String(1000), {}, False),
        ("sla_due_at", sa.DateTime(timezone=True), {}, True),
        ("escalated_at", sa.DateTime(timezone=True), {}, False),
        ("attempts", sa.Integer(), {"server_default": "0", "nullable": False}, False),
    ],
}


def _columnas(con, tabla: str) -> set[str]:
    return {c["name"] for c in sa.inspect(con).get_columns(tabla)}


def _indices(con, tabla: str) -> set[str]:
    return {i["name"] for i in sa.inspect(con).get_indexes(tabla)}


def upgrade() -> None:
    con = op.get_bind()
    tablas = set(sa.inspect(con).get_table_names())
    for tabla, cols in COLUMNAS.items():
        if tabla not in tablas:
            continue
        hay = _columnas(con, tabla)
        nuevas = [c for c in cols if c[0] not in hay]
        if not nuevas:
            continue
        with op.batch_alter_table(tabla) as t:
            for nombre, tipo, kw, _ in nuevas:
                args = [_fk(kw["fk"], tabla, nombre)] if "fk" in kw else []
                t.add_column(sa.Column(nombre, tipo, *args,
                                       nullable=kw.get("nullable", True),
                                       server_default=kw.get("server_default")))
        indices = _indices(con, tabla)
        for nombre, _tipo, _kw, indexar in nuevas:
            ix = f"ix_{tabla}_{nombre}"
            if indexar and ix not in indices:
                op.create_index(ix, tabla, [nombre])


def downgrade() -> None:
    con = op.get_bind()
    tablas = set(sa.inspect(con).get_table_names())
    for tabla, cols in reversed(list(COLUMNAS.items())):
        if tabla not in tablas:
            continue
        hay = _columnas(con, tabla)
        indices = _indices(con, tabla)
        for nombre, _tipo, _kw, indexar in cols:
            ix = f"ix_{tabla}_{nombre}"
            if indexar and ix in indices:
                op.drop_index(ix, table_name=tabla)
        quitar = [c[0] for c in cols if c[0] in hay]
        if quitar:
            with op.batch_alter_table(tabla) as t:
                for nombre in quitar:
                    t.drop_column(nombre)
