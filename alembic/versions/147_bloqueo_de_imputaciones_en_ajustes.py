"""El bloqueo de imputaciones vive en el ajuste de Admin, no en una columna.

Revisión 2026-11. `organizations.imputation_lockout_days` no lo editaba ninguna
pantalla ni endpoint, y al crear la empresa se llenaba con el valor del fichero:
tapaba para siempre el ajuste `DEFAULT_IMPUTATION_LOCKOUT_DAYS` de Admin, que
ya es por empresa. Un valor distinto del de por defecto se pasa al ajuste de su
empresa (sin pisar uno que ya exista) antes de borrar la columna.

Revision ID: 147_bloqueo_de_imputaciones_en_ajustes
Revises: 146_fuera_tablas_duplicadas
"""
import uuid

import sqlalchemy as sa
from alembic import op

revision = "147_bloqueo_de_imputaciones_en_ajustes"
down_revision = "146_fuera_tablas_duplicadas"
branch_labels = None
depends_on = None

CLAVE = "DEFAULT_IMPUTATION_LOCKOUT_DAYS"


def upgrade() -> None:
    con = op.get_bind()
    columnas = {c["name"] for c in sa.inspect(con).get_columns("organizations")}
    if "imputation_lockout_days" not in columnas:
        return
    from app.core.config import settings
    filas = con.execute(sa.text(
        "SELECT id, imputation_lockout_days FROM organizations WHERE imputation_lockout_days IS NOT NULL")).fetchall()
    for org_id, dias in filas:
        if dias == settings.DEFAULT_IMPUTATION_LOCKOUT_DAYS:
            continue
        ya = con.execute(sa.text("SELECT 1 FROM app_settings WHERE key = :k AND organization_id = :o"),
                         {"k": CLAVE, "o": org_id}).first()
        if not ya:
            con.execute(sa.text("INSERT INTO app_settings (id, organization_id, key, value) VALUES (:i, :o, :k, :v)"),
                        {"i": str(uuid.uuid4()), "o": org_id, "k": CLAVE, "v": str(dias)})
    with op.batch_alter_table("organizations") as t:
        t.drop_column("imputation_lockout_days")


def downgrade() -> None:
    with op.batch_alter_table("organizations") as t:
        t.add_column(sa.Column("imputation_lockout_days", sa.Integer(), nullable=True))
