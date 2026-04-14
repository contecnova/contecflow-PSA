"""013 — sem_config threshold calibration + schema notes

Actualiza los umbrales del motor semántico en filas existentes a los
valores calibrados 2026-Q1: critical 0.90, high 0.72, medium 0.58.
El threshold_low (0.45) no cambia.

Revision ID: 013_sem_config_threshold_calibration
Revises: 012_sem_config_priority_thresholds
Create Date: 2026-04-10
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision = "013_sem_config_threshold_calibration"
down_revision = "012_sem_config_priority_thresholds"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Update column defaults on the table to new calibrated values
    with op.batch_alter_table("sem_config") as batch_op:
        batch_op.alter_column(
            "threshold_critical",
            existing_type=sa.Float(),
            server_default="0.90",
        )
        batch_op.alter_column(
            "threshold_high",
            existing_type=sa.Float(),
            server_default="0.72",
        )
        batch_op.alter_column(
            "threshold_medium",
            existing_type=sa.Float(),
            server_default="0.58",
        )

    # Update any existing rows that still have the old default values
    op.execute(
        "UPDATE sem_config SET threshold_critical = 0.90 WHERE threshold_critical = 0.80"
    )
    op.execute(
        "UPDATE sem_config SET threshold_high = 0.72 WHERE threshold_high = 0.70"
    )
    op.execute(
        "UPDATE sem_config SET threshold_medium = 0.58 WHERE threshold_medium = 0.55"
    )


def downgrade() -> None:
    with op.batch_alter_table("sem_config") as batch_op:
        batch_op.alter_column(
            "threshold_critical",
            existing_type=sa.Float(),
            server_default="0.80",
        )
        batch_op.alter_column(
            "threshold_high",
            existing_type=sa.Float(),
            server_default="0.70",
        )
        batch_op.alter_column(
            "threshold_medium",
            existing_type=sa.Float(),
            server_default="0.55",
        )
    op.execute(
        "UPDATE sem_config SET threshold_critical = 0.80 WHERE threshold_critical = 0.90"
    )
    op.execute(
        "UPDATE sem_config SET threshold_high = 0.70 WHERE threshold_high = 0.72"
    )
    op.execute(
        "UPDATE sem_config SET threshold_medium = 0.55 WHERE threshold_medium = 0.58"
    )
