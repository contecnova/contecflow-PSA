"""Dominio propio de cada empresa (modo de entrada `subdomain`).

Revision multitenant 2026-11. Con `TENANT_ENTRY_MODE=subdomain` el host decide
la empresa: `<slug>.TENANT_ROOT_DOMAIN` o, si la empresa lo tiene, su dominio
propio (`app.cliente.com`). Ver app/services/entrada_service.py.
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "126_dominio_de_la_organizacion"
down_revision: Union[str, None] = "125_unicos_por_organizacion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("organizations")}
    if "domain" not in cols:
        with op.batch_alter_table("organizations") as batch:
            batch.add_column(sa.Column("domain", sa.String(255), nullable=True))
            batch.create_unique_constraint("uq_organizations_domain", ["domain"])


def downgrade() -> None:
    with op.batch_alter_table("organizations") as batch:
        batch.drop_constraint("uq_organizations_domain", type_="unique")
        batch.drop_column("domain")
