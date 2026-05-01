"""048 – Task movement log table

Crea la tabla task_movement_logs para registrar cada cambio de estado de tareas
con trazabilidad completa (quién, cuándo, desde, hacia, motivo).

Revision ID: 048_task_movement_log
Revises: 047_bi_collaboration_relational_tables, 044_merge_heads_rca_wizard_portal
Create Date: 2026-04-30
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "048_task_movement_log"
down_revision = ("047_bi_collaboration_relational_tables", "044_merge_heads_rca_wizard_portal")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task_movement_logs",
        sa.Column("id",          sa.String(36),  primary_key=True),
        sa.Column("task_id",     sa.String(36),  sa.ForeignKey("tasks.id",    ondelete="CASCADE"), nullable=False),
        sa.Column("project_id",  sa.String(36),  sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("moved_by_id", sa.String(36),  sa.ForeignKey("users.id",    ondelete="SET NULL"), nullable=True),
        sa.Column("from_status", sa.String(50),  nullable=True),
        sa.Column("to_status",   sa.String(50),  nullable=False),
        sa.Column("reason",      sa.Text,        nullable=True),
        sa.Column("moved_at",    sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_task_movement_logs_task_id",    "task_movement_logs", ["task_id"])
    op.create_index("ix_task_movement_logs_project_id", "task_movement_logs", ["project_id"])
    op.create_index("ix_task_movement_logs_moved_by_id","task_movement_logs", ["moved_by_id"])
    op.create_index("ix_task_movement_logs_moved_at",   "task_movement_logs", ["moved_at"])


def downgrade() -> None:
    op.drop_index("ix_task_movement_logs_moved_at",    table_name="task_movement_logs")
    op.drop_index("ix_task_movement_logs_moved_by_id", table_name="task_movement_logs")
    op.drop_index("ix_task_movement_logs_project_id",  table_name="task_movement_logs")
    op.drop_index("ix_task_movement_logs_task_id",     table_name="task_movement_logs")
    op.drop_table("task_movement_logs")
