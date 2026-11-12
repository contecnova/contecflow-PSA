"""MFA: intentos fallidos por reto y ultimo paso TOTP usado.

Auditoria 2026-11: el reto MFA vivia 5 minutos sin contador de fallos (solo
10/min por IP), y un codigo TOTP valido se podia reutilizar dentro de su
ventana. `failed_attempts` agota el reto; `mfa_last_timestep` impide el reuso.
"""
import sqlalchemy as sa
from alembic import op

revision = "157_mfa_intentos_y_reuso"
down_revision = "156_un_solo_motor_de_ingresos"
branch_labels = None
depends_on = None


def _columnas(tabla: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(tabla)}


def upgrade() -> None:
    if "failed_attempts" not in _columnas("mfa_challenges"):
        op.add_column("mfa_challenges", sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"))
    if "mfa_last_timestep" not in _columnas("users"):
        op.add_column("users", sa.Column("mfa_last_timestep", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as lote:
        lote.drop_column("mfa_last_timestep")
    with op.batch_alter_table("mfa_challenges") as lote:
        lote.drop_column("failed_attempts")
