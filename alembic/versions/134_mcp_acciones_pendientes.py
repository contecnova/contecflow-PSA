"""MCP: escrituras de agentes externos que esperan aprobación humana.

Revisión 2026-11: con MCP_WRITE_MODE=approval, la herramienta que escribe abre
una aprobación (entity_type «mcp_action») y se ejecuta solo si se aprueba.
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "134_mcp_acciones_pendientes"
down_revision: Union[str, None] = "133_calidad_kb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "mcp_pending_actions" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "mcp_pending_actions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=True, index=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("tool", sa.String(80), nullable=False),
        sa.Column("arguments", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending", index=True),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("approval_request_id", sa.String(36), nullable=True, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("mcp_pending_actions")
