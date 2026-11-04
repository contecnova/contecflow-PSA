"""Motor BPMN: instancias de proceso y sus pasos.

Auditoria 2026-11: /bpm era un editor sin ejecucion. `bpmn_instances` guarda
cada arranque y `bpmn_instance_steps` cada elemento que la ficha atraviesa
(historial) o en el que espera (tarea humana, temporizador, union paralela).
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "121_motor_bpmn"
down_revision: Union[str, None] = "120_roles_que_restringen"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tablas = sa.inspect(op.get_bind()).get_table_names()
    if "bpmn_instances" not in tablas:
        op.create_table(
            "bpmn_instances",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=True),
            sa.Column("process_id", sa.String(36), sa.ForeignKey("bpmn_processes.id", ondelete="CASCADE"), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="running"),
            sa.Column("variables", sa.Text(), nullable=True),
            sa.Column("error", sa.String(500), nullable=True),
            sa.Column("started_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_bpmn_instances_organization_id", "bpmn_instances", ["organization_id"])
        op.create_index("ix_bpmn_instances_process_id", "bpmn_instances", ["process_id"])
        op.create_index("ix_bpmn_instances_status", "bpmn_instances", ["status"])
    if "bpmn_instance_steps" not in tablas:
        op.create_table(
            "bpmn_instance_steps",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=True),
            sa.Column("instance_id", sa.String(36), sa.ForeignKey("bpmn_instances.id", ondelete="CASCADE"), nullable=False),
            sa.Column("element_id", sa.String(120), nullable=False),
            sa.Column("element_type", sa.String(40), nullable=False),
            sa.Column("name", sa.String(255), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("candidate_role", sa.String(40), nullable=True),
            sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("arrived", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("completed_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("result", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_bpmn_instance_steps_organization_id", "bpmn_instance_steps", ["organization_id"])
        op.create_index("ix_bpmn_instance_steps_instance_id", "bpmn_instance_steps", ["instance_id"])
        op.create_index("ix_bpmn_instance_steps_status", "bpmn_instance_steps", ["status"])


def downgrade() -> None:
    tablas = sa.inspect(op.get_bind()).get_table_names()
    for t in ("bpmn_instance_steps", "bpmn_instances"):
        if t in tablas:
            op.drop_table(t)
