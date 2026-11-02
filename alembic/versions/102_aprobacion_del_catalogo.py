"""Aprobacion del catalogo: el servicio que la pide no se atiende sin ella.

`ServiceItem.requires_approval` y `approval_user_id` existian y nadie los
comprobaba. Ahora el ticket de ese servicio nace con `approval_status`
pendiente y su decision queda en `sd_ticket_approvals`.
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "102_aprobacion_del_catalogo"
down_revision: Union[str, None] = "101_correo_entrante"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "approval_status" not in {c["name"] for c in insp.get_columns("sd_tickets")}:
        with op.batch_alter_table("sd_tickets") as batch:
            batch.add_column(sa.Column("approval_status", sa.String(20), nullable=True))
        op.create_index("ix_sd_tickets_approval_status", "sd_tickets", ["approval_status"])
    if "sd_ticket_approvals" not in insp.get_table_names():
        op.create_table(
            "sd_ticket_approvals",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=True),
            sa.Column("ticket_id", sa.String(36), sa.ForeignKey("sd_tickets.id", ondelete="CASCADE"), nullable=False),
            sa.Column("approver_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("comment", sa.Text(), nullable=True),
            sa.Column("decided_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        for col in ("organization_id", "ticket_id", "approver_user_id", "status"):
            op.create_index(f"ix_sd_ticket_approvals_{col}", "sd_ticket_approvals", [col])


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "sd_ticket_approvals" in insp.get_table_names():
        op.drop_table("sd_ticket_approvals")
    if "approval_status" in {c["name"] for c in insp.get_columns("sd_tickets")}:
        op.drop_index("ix_sd_tickets_approval_status", table_name="sd_tickets")
        with op.batch_alter_table("sd_tickets") as batch:
            batch.drop_column("approval_status")
