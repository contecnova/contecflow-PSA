"""MFA: un solo sistema TOTP (`users.mfa_secret` / `users.mfa_enabled`).

Auditoria 2026-11. Habia dos: el de `/api/v1/auth/mfa/*` (en `users`, el que
exige el login) y el de la pantalla /mfa (`/api/v1/mfa/*`, tabla `mfa_configs`),
que el login no miraba: quien activo el 2FA desde esa pantalla antes de que se
sincronizasen creia estar protegido y no lo estaba. Se retira el segundo.

upgrade:
  * anade `users.mfa_verified_at` (si no esta);
  * por cada `mfa_configs` activada y con secreto, si el usuario no tiene ya
    TOTP canonico (`mfa_enabled` y `mfa_secret`), copia el secreto a
    `users.mfa_secret` y pone `mfa_enabled = true`. El secreto se copia tal cual:
    los dos sitios cifran con `encrypt_value` y descifran con `decrypt_value`
    (lo antiguo en claro tambien se lee igual en los dos);
  * los codigos de respaldo sin usar de esas configuraciones pasan a ser del
    usuario: `mfa_backup_codes` se rehace con `user_id` en vez de `mfa_id`;
  * borra `mfa_configs`: tras esta revision no la lee nadie.

Idempotente: repetirla no duplica ni falla (si `mfa_configs` ya no esta, solo
comprueba la columna). SQLite y PostgreSQL.

Revision ID: 160_mfa_un_solo_sistema
Revises: 159_jira_una_sola_configuracion
"""
import sqlalchemy as sa
from alembic import op

revision = "160_mfa_un_solo_sistema"
down_revision = "159_jira_una_sola_configuracion"
branch_labels = None
depends_on = None


def _tablas(con) -> set[str]:
    return set(sa.inspect(con).get_table_names())


def _columnas(con, tabla: str) -> set[str]:
    return {c["name"] for c in sa.inspect(con).get_columns(tabla)}


def _crear_codigos() -> None:
    op.create_table(
        "mfa_backup_codes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code_hash", sa.String(128), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_mfa_backup_codes_organization_id", "mfa_backup_codes", ["organization_id"])
    op.create_index("ix_mfa_backup_codes_user_id", "mfa_backup_codes", ["user_id"])


def upgrade() -> None:
    con = op.get_bind()
    if "mfa_verified_at" not in _columnas(con, "users"):
        op.add_column("users", sa.Column("mfa_verified_at", sa.DateTime(timezone=True), nullable=True))

    tablas = _tablas(con)
    codigos: list = []
    if "mfa_configs" in tablas:
        activas = con.execute(sa.text(
            "SELECT user_id, totp_secret, verified_at FROM mfa_configs "
            "WHERE is_enabled = :si AND totp_secret IS NOT NULL AND totp_secret <> ''"),
            {"si": True}).fetchall()
        for c in activas:
            u = con.execute(sa.text("SELECT mfa_enabled, mfa_secret, mfa_verified_at FROM users WHERE id = :id"),
                            {"id": c.user_id}).fetchone()
            if u is None:
                continue
            if not (u.mfa_enabled and u.mfa_secret):
                con.execute(sa.text(
                    "UPDATE users SET mfa_secret = :s, mfa_enabled = :si, mfa_verified_at = :v WHERE id = :id"),
                    {"s": c.totp_secret, "si": True, "v": c.verified_at, "id": c.user_id})
            elif u.mfa_secret == c.totp_secret and u.mfa_verified_at is None and c.verified_at is not None:
                con.execute(sa.text("UPDATE users SET mfa_verified_at = :v WHERE id = :id"),
                            {"v": c.verified_at, "id": c.user_id})
        if "mfa_backup_codes" in tablas and "mfa_id" in _columnas(con, "mfa_backup_codes"):
            # Los que valian al entrar: sin usar y de una configuracion activa.
            codigos = con.execute(sa.text(
                "SELECT b.id, b.organization_id, c.user_id, b.code_hash, b.created_at "
                "FROM mfa_backup_codes b JOIN mfa_configs c ON c.id = b.mfa_id "
                "WHERE c.is_enabled = :si AND b.used_at IS NULL"), {"si": True}).fetchall()

    if "mfa_backup_codes" in tablas and "mfa_id" in _columnas(con, "mfa_backup_codes"):
        op.drop_table("mfa_backup_codes")
        _crear_codigos()
        for b in codigos:
            con.execute(sa.text(
                "INSERT INTO mfa_backup_codes (id, organization_id, user_id, code_hash, used_at, created_at) "
                "VALUES (:id, :org, :u, :h, NULL, :c)"),
                {"id": b.id, "org": b.organization_id, "u": b.user_id, "h": b.code_hash, "c": b.created_at})
    elif "mfa_backup_codes" not in _tablas(con):
        _crear_codigos()

    if "mfa_configs" in _tablas(con):
        op.drop_table("mfa_configs")


def downgrade() -> None:
    # Los secretos ya estan en `users`; no se devuelven a una tabla que el login
    # no mira. Irreversible a proposito, como la 146.
    pass
