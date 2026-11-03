"""Los datos propios de cada clase de CI, configurables por organizacion.

Auditoria 2026-11: estaban fijos en la pantalla de la CMDB. Tabla vacia: cada
organizacion usa los de fabrica hasta que guarda la primera clase
(`app/services/service_desk/cmdb_clases.py`).
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "114_clases_de_ci_configurables"
down_revision: Union[str, None] = "113_contratos_de_soporte_uc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sd_ci_class_fields",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=True, index=True),
        sa.Column("ci_type", sa.String(30), nullable=False),
        sa.Column("key", sa.String(50), nullable=False),
        sa.Column("label", sa.String(100), nullable=True),
        sa.Column("field_type", sa.String(10), nullable=False, server_default="text"),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.UniqueConstraint("organization_id", "ci_type", "key", name="uq_sd_ci_class_field"),
    )


def downgrade() -> None:
    op.drop_table("sd_ci_class_fields")
