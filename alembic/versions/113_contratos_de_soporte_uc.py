"""UC: el plazo del proveedor mientras el ticket espera a un tercero.

Auditoria 2026-11: no habia contratos de soporte. Los proveedores y sus
contratos existian en ALM, pero un contrato no tenia plazo y nada medía cuanto
tardaba un tercero con un ticket que esperaba por el.

- `alm_contracts.resolution_hours`: el plazo del proveedor (vacio, no es UC).
- `sd_tickets`: el contrato aplicado y su reloj (inicio, vencimiento,
  incumplido), como el OLA de las colas.
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "113_contratos_de_soporte_uc"
down_revision: Union[str, None] = "112_acento_del_tema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("alm_contracts") as batch:
        batch.add_column(sa.Column("resolution_hours", sa.Float, nullable=True))
    with op.batch_alter_table("sd_tickets") as batch:
        batch.add_column(sa.Column("uc_contract_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("uc_started_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("uc_due", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("uc_breached", sa.Boolean, nullable=False, server_default=sa.false()))
        batch.create_foreign_key("fk_sd_tickets_uc_contract", "alm_contracts", ["uc_contract_id"], ["id"],
                                 ondelete="SET NULL")


def downgrade() -> None:
    with op.batch_alter_table("sd_tickets") as batch:
        batch.drop_constraint("fk_sd_tickets_uc_contract", type_="foreignkey")
        for c in ("uc_breached", "uc_due", "uc_started_at", "uc_contract_id"):
            batch.drop_column(c)
    with op.batch_alter_table("alm_contracts") as batch:
        batch.drop_column("resolution_hours")
