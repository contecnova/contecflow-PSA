"""Automatizaciones que se disparan: disparador como texto, bandeja de eventos.

Auditoria 2026-11:
- `automation_rules.trigger_type` era el enum de Postgres `triggertype` con 14
  valores, y la pantalla ofrecia 64: guardar cualquiera de los otros 52 daba
  error. Pasa a VARCHAR(64); el catalogo valido lo comprueba la API.
- `automation_rules.organization_id` estaba a NULL en las reglas sembradas y
  en las creadas sin contexto: se rellena con la organizacion del proyecto o,
  si no hay, la de quien la creo. Sin ella la regla no sabe a quien pertenece.
- `automation_executions.dedupe_key`: el barrido periodico ve la misma tarea
  vencida en cada pasada; la regla actua una vez por clave.
- `automation_events`: bandeja de salida de los cambios que disparan reglas.
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "118_automatizaciones_que_disparan"
down_revision: Union[str, None] = "117_esign_secretos_cifrados"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if bind.dialect.name == "postgresql":
        # La accion «crear alerta» usaba siempre `budget_exceeded`.
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE alerttype ADD VALUE IF NOT EXISTS 'automation'")
        op.execute("ALTER TABLE automation_rules ALTER COLUMN trigger_type TYPE VARCHAR(64) "
                   "USING trigger_type::text")
        op.execute("DROP TYPE IF EXISTS triggertype")
    else:
        with op.batch_alter_table("automation_rules") as batch:
            batch.alter_column("trigger_type", type_=sa.String(64), existing_nullable=False)

    op.execute("""
        UPDATE automation_rules SET organization_id = (
            SELECT p.organization_id FROM projects p WHERE p.id = automation_rules.project_id)
        WHERE organization_id IS NULL AND project_id IS NOT NULL
    """)
    op.execute("""
        UPDATE automation_rules SET organization_id = (
            SELECT u.organization_id FROM users u WHERE u.id = automation_rules.created_by)
        WHERE organization_id IS NULL AND created_by IS NOT NULL
    """)

    cols = {c["name"] for c in insp.get_columns("automation_executions")}
    if "dedupe_key" not in cols:
        with op.batch_alter_table("automation_executions") as batch:
            batch.add_column(sa.Column("dedupe_key", sa.String(255), nullable=True))
            batch.create_index("ix_automation_executions_dedupe_key", ["dedupe_key"])

    if "automation_events" not in insp.get_table_names():
        op.create_table(
            "automation_events",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=True),
            sa.Column("trigger_type", sa.String(64), nullable=False),
            sa.Column("context", sa.Text(), nullable=True),
            sa.Column("depth", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("error", sa.String(500), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_automation_events_organization_id", "automation_events", ["organization_id"])
        op.create_index("ix_automation_events_status", "automation_events", ["status"])
        op.create_index("ix_automation_events_created_at", "automation_events", ["created_at"])


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "automation_events" in insp.get_table_names():
        op.drop_table("automation_events")
    cols = {c["name"] for c in insp.get_columns("automation_executions")}
    if "dedupe_key" in cols:
        with op.batch_alter_table("automation_executions") as batch:
            batch.drop_index("ix_automation_executions_dedupe_key")
            batch.drop_column("dedupe_key")
    # El disparador se queda como texto: volver al enum de 14 perderia las
    # reglas guardadas con los disparadores nuevos.
