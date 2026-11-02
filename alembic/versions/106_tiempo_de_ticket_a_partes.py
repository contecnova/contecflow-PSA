"""El tiempo de un ticket enlaza con la imputacion que genero en los partes.

`sd_ticket_time_logs.imputation_id`: el tiempo de un ticket con proyecto pasa a
los partes del agente (y de ahi a la factura si es facturable). Antes se
quedaba en el ticket y el PSA no se enteraba.
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "106_tiempo_de_ticket_a_partes"
down_revision: Union[str, None] = "105_base_de_conocimiento"
branch_labels = None
depends_on = None


def upgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("sd_ticket_time_logs")}
    if "imputation_id" in cols:
        return
    with op.batch_alter_table("sd_ticket_time_logs") as batch:
        batch.add_column(sa.Column("imputation_id", sa.String(36), nullable=True))
        batch.create_foreign_key("fk_sd_ticket_time_logs_imputation_id", "imputations",
                                 ["imputation_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_sd_ticket_time_logs_imputation_id", "sd_ticket_time_logs", ["imputation_id"])


def downgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("sd_ticket_time_logs")}
    if "imputation_id" not in cols:
        return
    op.drop_index("ix_sd_ticket_time_logs_imputation_id", table_name="sd_ticket_time_logs")
    with op.batch_alter_table("sd_ticket_time_logs") as batch:
        batch.drop_constraint("fk_sd_ticket_time_logs_imputation_id", type_="foreignkey")
        batch.drop_column("imputation_id")
