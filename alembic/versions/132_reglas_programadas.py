"""Automatizaciones programadas: expresión cron y próxima ejecución.

Revisión 2026-11: una regla con disparador «scheduled» corre según su cron (en
la zona horaria de la empresa), sin esperar a ningún cambio.
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "132_reglas_programadas"
down_revision: Union[str, None] = "131_fuera_de_la_oficina"
branch_labels = None
depends_on = None


def upgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("automation_rules")}
    with op.batch_alter_table("automation_rules") as batch:
        if "schedule_cron" not in cols:
            batch.add_column(sa.Column("schedule_cron", sa.String(100), nullable=True))
        if "next_run_at" not in cols:
            batch.add_column(sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_automation_rules_next_run_at", "automation_rules", ["next_run_at"], if_not_exists=True)


def downgrade() -> None:
    op.drop_index("ix_automation_rules_next_run_at", table_name="automation_rules", if_exists=True)
    with op.batch_alter_table("automation_rules") as batch:
        batch.drop_column("next_run_at")
        batch.drop_column("schedule_cron")
