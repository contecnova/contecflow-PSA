"""Añade clients.timezone para los cortes de periodo por cliente.

Auditoría 2026-08 (hallazgo 14). Los cortes de periodo de facturación e informes
se calculaban con `date.today()`, es decir, en la zona horaria del servidor. En
una aplicación multi-tenant donde cada organización tiene su zona, eso significa
que el «agosto» de una factura no coincidía con el mes natural del cliente: una
organización en Madrid perdía la primera hora del 1 de agosto y se le colaba la
primera hora del 1 de septiembre.

La decisión de negocio es que el corte lo manda la zona del CLIENTE del proyecto
—una factura tiene un periodo único, no uno por empleado—, así que el modelo
`Client` necesita su propia zona. No la tenía.

NULL significa «hereda la de la organización», que es el comportamiento anterior
para los clientes existentes: esta revisión no cambia ningún cálculo hasta que
alguien rellene la zona de un cliente concreto. Ver
app/core/timeutil.py::zone_for_client.
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "090_client_timezone"
down_revision: Union[str, None] = "089_schema_gap_missing_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # nullable=True a propósito: NULL = heredar de la organización. Poner un
    # valor por defecto obligaría a elegir una zona para clientes de los que no
    # se sabe dónde están, y eso desplazaría sus cierres en silencio.
    op.add_column("clients", sa.Column("timezone", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("clients", "timezone")
