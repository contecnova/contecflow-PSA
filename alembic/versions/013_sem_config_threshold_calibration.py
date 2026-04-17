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
    # Usar valores de calibración desde variables de entorno si existen
    import os
    threshold_critical = os.getenv("SEM_THRESHOLD_CRITICAL", "0.90")
    threshold_high = os.getenv("SEM_THRESHOLD_HIGH", "0.72")
    threshold_medium = os.getenv("SEM_THRESHOLD_MEDIUM", "0.58")

    with op.batch_alter_table("sem_config") as batch_op:
        batch_op.alter_column(
            "threshold_critical",
            existing_type=sa.Float(),
            server_default=threshold_critical,
        )
        batch_op.alter_column(
            "threshold_high",
            existing_type=sa.Float(),
            server_default=threshold_high,
        )
        batch_op.alter_column(
            "threshold_medium",
            existing_type=sa.Float(),
            server_default=threshold_medium,
        )

    # Update any existing rows that still have the old default values
    op.execute(
        f"UPDATE sem_config SET threshold_critical = {threshold_critical} WHERE threshold_critical = 0.80"
    )
    op.execute(
        f"UPDATE sem_config SET threshold_high = {threshold_high} WHERE threshold_high = 0.70"
    )
    op.execute(
        f"UPDATE sem_config SET threshold_medium = {threshold_medium} WHERE threshold_medium = 0.55"
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
