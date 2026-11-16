"""BPM: decisiones manuales y motivo de fallo traducible.

Revisión BPM 2026-11-16.

- `bpmn_instance_steps.wait_kind`: por qué espera un paso (task, decision,
  timer, join). Las compuertas exclusivas sin condiciones pasan a ser una
  decisión que toma una persona desde la bandeja; antes la instancia fallaba
  siempre en ellas (el editor no permite escribir condiciones).
- `bpmn_instances.error_code` / `error_params`: el motivo del fallo como código
  para que la interfaz lo traduzca en los tres idiomas.

Revision ID: 169_bpmn_decisiones_y_codigos_de_error
Revises: 168_indice_unico_procesos_bpmn
"""
import sqlalchemy as sa
from alembic import op

revision = "169_bpmn_decisiones_y_codigos_de_error"
down_revision = "168_indice_unico_procesos_bpmn"
branch_labels = None
depends_on = None


def _columnas(con, tabla: str) -> set[str]:
    return {c["name"] for c in sa.inspect(con).get_columns(tabla)}


def upgrade() -> None:
    con = op.get_bind()
    tablas = set(sa.inspect(con).get_table_names())
    if "bpmn_instance_steps" in tablas and "wait_kind" not in _columnas(con, "bpmn_instance_steps"):
        with op.batch_alter_table("bpmn_instance_steps") as t:
            t.add_column(sa.Column("wait_kind", sa.String(20), nullable=True))
        # Los pasos ya existentes: lo que el motor anterior dejaba esperando.
        op.execute("UPDATE bpmn_instance_steps SET wait_kind = 'task' "
                   "WHERE element_type IN ('task', 'userTask', 'manualTask')")
        op.execute("UPDATE bpmn_instance_steps SET wait_kind = 'timer' "
                   "WHERE element_type = 'intermediateCatchEvent'")
        op.execute("UPDATE bpmn_instance_steps SET wait_kind = 'join' "
                   "WHERE element_type = 'parallelGateway' AND arrived > 1")
    if "bpmn_instances" in tablas:
        columnas = _columnas(con, "bpmn_instances")
        with op.batch_alter_table("bpmn_instances") as t:
            if "error_code" not in columnas:
                t.add_column(sa.Column("error_code", sa.String(60), nullable=True))
            if "error_params" not in columnas:
                t.add_column(sa.Column("error_params", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("bpmn_instances") as t:
        t.drop_column("error_params")
        t.drop_column("error_code")
    with op.batch_alter_table("bpmn_instance_steps") as t:
        t.drop_column("wait_kind")
