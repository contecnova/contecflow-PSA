"""Políticas de cuenta y registro de auditoría inmutable (23-11-2026).

docs/seguridad/politicas_de_cuenta.md:

1. `users`: `password_changed_at`, `password_must_change` (NOT NULL, false),
   `password_temporary_until`, `locked_until` y `mfa_grace_started_at`.
2. `user_sessions.session_key` (con índice): clave estable de la sesión que va
   en el token de acceso como `sid`. Se rellena con el jti actual de cada
   sesión, que es lo que el refresco usa como `sid` hasta la siguiente rotación.
3. Tablas nuevas: `password_history`, `trusted_devices`,
   `security_change_requests`, `access_review_campaigns`, `access_review_items`
   y `audit_log_purge_permits`.
4. Triggers que niegan UPDATE y DELETE en `audit_logs` (hallazgo B.1 del informe
   05 de la auditoría 2026-11-22): `app/db/auditoria_inmutable.py`, en Postgres
   (plpgsql, también TRUNCATE) y SQLite (RAISE(ABORT)).

SQLite: `batch_alter_table` para las columnas. PostgreSQL: ALTER directos. La
RLS de las tablas nuevas la aplica `env.py` tras el `upgrade` (tienen
`organization_id`).

Deshacer real: quita los triggers, las tablas y las columnas.

Idempotente: cada paso mira antes si ya está hecho.

Revision ID: 199_seguridad_de_cuentas
Revises: 198_cambios_estandar_y_portal
"""
import sqlalchemy as sa
from alembic import op

revision = "199_seguridad_de_cuentas"
down_revision = "198_cambios_estandar_y_portal"
branch_labels = None
depends_on = None

_TZ = sa.DateTime(timezone=True)

COLUMNAS_DE_USERS = (
    ("password_changed_at", lambda: sa.Column("password_changed_at", _TZ, nullable=True)),
    ("password_must_change", lambda: sa.Column("password_must_change", sa.Boolean(), nullable=False,
                                               server_default=sa.false())),
    ("password_temporary_until", lambda: sa.Column("password_temporary_until", _TZ, nullable=True)),
    ("locked_until", lambda: sa.Column("locked_until", _TZ, nullable=True)),
    ("mfa_grace_started_at", lambda: sa.Column("mfa_grace_started_at", _TZ, nullable=True)),
)

TABLAS = ("access_review_items", "access_review_campaigns", "security_change_requests", "trusted_devices",
          "password_history", "audit_log_purge_permits")


def _insp():
    return sa.inspect(op.get_bind())


def _tablas() -> set:
    return set(_insp().get_table_names())


def _columnas(tabla: str) -> set:
    return {c["name"] for c in _insp().get_columns(tabla)}


def _indices(tabla: str) -> set:
    return {i["name"] for i in _insp().get_indexes(tabla)}


def _org():
    return sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                     nullable=True)


def _crear_tablas() -> None:
    hay = _tablas()
    if "password_history" not in hay:
        op.create_table(
            "password_history",
            sa.Column("id", sa.String(36), primary_key=True),
            _org(),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("password_hash", sa.String(255), nullable=False),
            sa.Column("created_at", _TZ, server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_password_history_organization_id", "password_history", ["organization_id"])
        op.create_index("ix_password_history_user_id", "password_history", ["user_id"])
    if "trusted_devices" not in hay:
        op.create_table(
            "trusted_devices",
            sa.Column("id", sa.String(36), primary_key=True),
            _org(),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("token_hash", sa.String(64), nullable=False),
            sa.Column("device_name", sa.String(255), nullable=True),
            sa.Column("ip_address", sa.String(64), nullable=True),
            sa.Column("created_at", _TZ, server_default=sa.func.now(), nullable=False),
            sa.Column("last_used_at", _TZ, nullable=True),
            sa.Column("expires_at", _TZ, nullable=False),
            sa.Column("revoked_at", _TZ, nullable=True),
            sa.Column("revoke_reason", sa.String(120), nullable=True),
        )
        op.create_index("ix_trusted_devices_organization_id", "trusted_devices", ["organization_id"])
        op.create_index("ix_trusted_devices_user_id", "trusted_devices", ["user_id"])
        op.create_index("ix_trusted_devices_token_hash", "trusted_devices", ["token_hash"], unique=True)
    if "security_change_requests" not in hay:
        op.create_table(
            "security_change_requests",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                      nullable=False),
            sa.Column("kind", sa.String(40), nullable=False),
            sa.Column("target_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
            sa.Column("payload", sa.Text(), nullable=True),
            sa.Column("reason", sa.String(500), nullable=True),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("requested_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("requested_at", _TZ, server_default=sa.func.now(), nullable=False),
            sa.Column("decided_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("decided_at", _TZ, nullable=True),
            sa.Column("decision_comment", sa.String(500), nullable=True),
        )
        for col in ("organization_id", "target_user_id", "status", "requested_by"):
            op.create_index(f"ix_security_change_requests_{col}", "security_change_requests", [col])
    if "access_review_campaigns" not in hay:
        op.create_table(
            "access_review_campaigns",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                      nullable=False),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("due_at", _TZ, nullable=True),
            sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", _TZ, server_default=sa.func.now(), nullable=False),
            sa.Column("closed_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("closed_at", _TZ, nullable=True),
        )
        op.create_index("ix_access_review_campaigns_organization_id", "access_review_campaigns", ["organization_id"])
        op.create_index("ix_access_review_campaigns_status", "access_review_campaigns", ["status"])
    if "access_review_items" not in hay:
        op.create_table(
            "access_review_items",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                      nullable=False),
            sa.Column("campaign_id", sa.String(36), sa.ForeignKey("access_review_campaigns.id", ondelete="CASCADE"),
                      nullable=False),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("reviewer_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("snapshot", sa.Text(), nullable=True),
            sa.Column("decision", sa.String(20), nullable=False),
            sa.Column("comment", sa.String(1000), nullable=True),
            sa.Column("decided_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("decided_at", _TZ, nullable=True),
            sa.Column("applied_at", _TZ, nullable=True),
        )
        for col in ("organization_id", "campaign_id", "user_id", "reviewer_id"):
            op.create_index(f"ix_access_review_items_{col}", "access_review_items", [col])
        op.create_index("ix_access_review_items_reviewer_decision", "access_review_items", ["reviewer_id", "decision"])
    if "audit_log_purge_permits" not in hay:
        op.create_table(
            "audit_log_purge_permits",
            sa.Column("organization_id", sa.String(36), primary_key=True),
            sa.Column("reason", sa.String(200), nullable=True),
            sa.Column("created_at", _TZ, server_default=sa.func.now(), nullable=False),
            sa.Column("uses", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        )


def upgrade() -> None:
    hay = _columnas("users")
    faltan = [f() for nombre, f in COLUMNAS_DE_USERS if nombre not in hay]
    if faltan:
        with op.batch_alter_table("users") as b:
            for col in faltan:
                b.add_column(col)
    if "session_key" not in _columnas("user_sessions"):
        with op.batch_alter_table("user_sessions") as b:
            b.add_column(sa.Column("session_key", sa.String(36), nullable=True))
    if "ix_user_sessions_session_key" not in _indices("user_sessions"):
        op.create_index("ix_user_sessions_session_key", "user_sessions", ["session_key"])
    op.execute("UPDATE user_sessions SET session_key = refresh_token_jti WHERE session_key IS NULL")
    _crear_tablas()
    from app.db import auditoria_inmutable
    auditoria_inmutable.instalar(op.get_bind())


def downgrade() -> None:
    from app.db import auditoria_inmutable
    auditoria_inmutable.desinstalar(op.get_bind())
    hay = _tablas()
    for t in TABLAS:
        if t in hay:
            op.drop_table(t)
    if "ix_user_sessions_session_key" in _indices("user_sessions"):
        op.drop_index("ix_user_sessions_session_key", table_name="user_sessions")
    if "session_key" in _columnas("user_sessions"):
        with op.batch_alter_table("user_sessions") as b:
            b.drop_column("session_key")
    hay = _columnas("users")
    sobran = [n for n, _ in COLUMNAS_DE_USERS if n in hay]
    if sobran:
        with op.batch_alter_table("users") as b:
            for n in sobran:
                b.drop_column(n)
