"""UC: el plazo de respuesta del proveedor, ademas del de resolucion.

Auditoria 2026-11: el UC solo medía la resolucion porque nada registraba
cuando contestaba el proveedor. Ahora lo anota el agente en el ticket.
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "115_uc_plazo_de_respuesta"
down_revision: Union[str, None] = "114_clases_de_ci_configurables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("alm_contracts") as batch:
        batch.add_column(sa.Column("response_hours", sa.Float, nullable=True))
    with op.batch_alter_table("sd_tickets") as batch:
        batch.add_column(sa.Column("uc_vendor_responded_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("uc_response_due", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("uc_response_breached", sa.Boolean, nullable=False, server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table("sd_tickets") as batch:
        for c in ("uc_response_breached", "uc_response_due", "uc_vendor_responded_at"):
            batch.drop_column(c)
    with op.batch_alter_table("alm_contracts") as batch:
        batch.drop_column("response_hours")
