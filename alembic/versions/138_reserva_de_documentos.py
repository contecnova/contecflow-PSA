"""Reserva de documentos para editar (check-out / check-in).

Revisión 2026-11 (lo que contecmind tenía): mientras alguien tiene un documento
reservado, nadie más sube versión, cambia sus datos ni lo archiva.
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "138_reserva_documentos"
down_revision: Union[str, None] = "137_cadena_auditoria"
branch_labels = None
depends_on = None


def upgrade() -> None:
    hay = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("documents")}
    if "checked_out_by" not in hay:
        op.add_column("documents", sa.Column("checked_out_by", sa.String(36),
                                             sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True))
        op.create_index("ix_documents_checked_out_by", "documents", ["checked_out_by"])
    if "checked_out_at" not in hay:
        op.add_column("documents", sa.Column("checked_out_at", sa.DateTime(timezone=True), nullable=True))
    if "checkout_expires_at" not in hay:
        op.add_column("documents", sa.Column("checkout_expires_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "checkout_expires_at")
    op.drop_column("documents", "checked_out_at")
    op.drop_index("ix_documents_checked_out_by", table_name="documents")
    op.drop_column("documents", "checked_out_by")
