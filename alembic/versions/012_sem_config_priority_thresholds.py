"""012 — sem_config priority thresholds + history decay

Agrega columnas de umbrales por prioridad y decaimiento temporal
al motor de asignación semántica.

Revision ID: 012_sem_config_priority_thresholds
Revises: 011_ai_governance_guardrails
Create Date: 2026-04-10
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision = "012_sem_config_priority_thresholds"
down_revision = "011_ai_governance_guardrails"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sem_config",
        sa.Column("threshold_critical", sa.Float(), nullable=True, server_default="0.80"),
    )
    op.add_column(
        "sem_config",
        sa.Column("threshold_high", sa.Float(), nullable=True, server_default="0.70"),
    )
    op.add_column(
        "sem_config",
        sa.Column("threshold_medium", sa.Float(), nullable=True, server_default="0.55"),
    )
    op.add_column(
        "sem_config",
        sa.Column("threshold_low", sa.Float(), nullable=True, server_default="0.45"),
    )
    op.add_column(
        "sem_config",
        sa.Column("history_decay_days", sa.Float(), nullable=True, server_default="90.0"),
    )


def downgrade() -> None:
    op.drop_column("sem_config", "threshold_critical")
    op.drop_column("sem_config", "threshold_high")
    op.drop_column("sem_config", "threshold_medium")
    op.drop_column("sem_config", "threshold_low")
    op.drop_column("sem_config", "history_decay_days")
