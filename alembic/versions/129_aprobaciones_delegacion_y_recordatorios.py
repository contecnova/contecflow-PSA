"""Aprobaciones: a quien se delega un paso y el ultimo recordatorio.

Revision 2026-11: la delegacion avisaba al delegado pero no le dejaba decidir
(no se guardaba a quien se delegaba); `reminder_hours` se guardaba y nadie
lo leia.
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "129_aprobaciones_delegacion"
down_revision: Union[str, None] = "128_baja_de_empresa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "delegate_to" not in {c["name"] for c in insp.get_columns("approval_decisions")}:
        with op.batch_alter_table("approval_decisions") as batch:
            batch.add_column(sa.Column("delegate_to", sa.String(36), nullable=True))
            batch.create_foreign_key("fk_approval_decisions_delegate_to", "users", ["delegate_to"], ["id"])
    if "last_reminder_at" not in {c["name"] for c in insp.get_columns("approval_requests")}:
        with op.batch_alter_table("approval_requests") as batch:
            batch.add_column(sa.Column("last_reminder_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("approval_requests") as batch:
        batch.drop_column("last_reminder_at")
    with op.batch_alter_table("approval_decisions") as batch:
        batch.drop_constraint("fk_approval_decisions_delegate_to", type_="foreignkey")
        batch.drop_column("delegate_to")
