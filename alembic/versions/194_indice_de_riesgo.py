"""Índice de riesgo y gestión de vulnerabilidades (22-11-2026).

Diseño: `docs/CMDB_SOFTWARE_Y_VULNERABILIDADES.md`, §11. Modelos:
`app/models/cmdb_riesgo.py` y columnas nuevas en `app/models/cmdb_software.py`.

Tablas nuevas: `sw_risk_snapshots` (histórico diario del índice por ámbito),
`sw_compensating_controls`, `sw_exploit_events`, `sw_saved_views` y
`sw_risk_alert_log`.

Columnas nuevas: `sw_config.risk_settings`, `sw_findings.detected_by`,
`sw_findings.exploit_attempts`, `sw_findings.last_exploit_at`,
`sw_findings.risk_points`, `sw_instances.exposure_source`.

Idempotente: cada tabla, columna e índice solo se crea si no existe. La
política RLS de las tablas nuevas la aplica `env.py` (`app/db/rls.py`).
Downgrade: borra las tablas y columnas nuevas (con sus datos).

Revision ID: 194_indice_de_riesgo
Revises: 193_clientes_internos
"""
import sqlalchemy as sa
from alembic import op

revision = "194_indice_de_riesgo"
down_revision = "193_clientes_internos"
branch_labels = None
depends_on = None

S = sa.String
T = sa.Text
DT = sa.DateTime(timezone=True)


def _insp():
    return sa.inspect(op.get_bind())


def _tablas() -> set:
    return set(_insp().get_table_names())


def _columnas(tabla: str) -> set:
    return {c["name"] for c in _insp().get_columns(tabla)}


def _fk(nombre, tabla, ondelete="SET NULL", nullable=True):
    return sa.Column(nombre, S(36), sa.ForeignKey(f"{tabla}.id", ondelete=ondelete), nullable=nullable)


def _crear(nombre, *columnas, indices=(), unicos=()):
    if nombre in _tablas():
        return
    op.create_table(
        nombre,
        sa.Column("id", S(36), primary_key=True),
        sa.Column("organization_id", S(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True),
        *columnas,
        *(sa.UniqueConstraint(*cols, name=n) for n, cols in unicos),
    )
    for c in ("organization_id", *indices):
        op.create_index(f"ix_{nombre}_{c}", nombre, [c])


def _columna(tabla: str, columna: sa.Column) -> None:
    if tabla in _tablas() and columna.name not in _columnas(tabla):
        with op.batch_alter_table(tabla) as b:
            b.add_column(columna)


COLUMNAS = (
    ("sw_config", lambda: sa.Column("risk_settings", T, nullable=True)),
    ("sw_findings", lambda: sa.Column("detected_by", T, nullable=True)),
    ("sw_findings", lambda: sa.Column("exploit_attempts", sa.Integer, nullable=False, server_default="0")),
    ("sw_findings", lambda: sa.Column("last_exploit_at", DT, nullable=True)),
    ("sw_findings", lambda: sa.Column("risk_points", sa.Float, nullable=True)),
    ("sw_instances", lambda: sa.Column("exposure_source", S(10), nullable=True)),
)


def upgrade() -> None:
    for tabla, columna in COLUMNAS:
        _columna(tabla, columna())

    _crear("sw_risk_snapshots",
           sa.Column("scope_type", S(12), nullable=False),
           sa.Column("scope_id", S(36), nullable=False, server_default=""),
           sa.Column("day", sa.Date, nullable=False),
           sa.Column("score", sa.Float, nullable=False, server_default="0"),
           sa.Column("accepted_score", sa.Float, nullable=False, server_default="0"),
           sa.Column("factors", T), sa.Column("counts", T),
           sa.Column("computed_at", DT, server_default=sa.func.now()),
           indices=("scope_type", "scope_id", "day"),
           unicos=(("uq_sw_risk_snapshots_scope_day", ("organization_id", "scope_type", "scope_id", "day")),))

    _crear("sw_compensating_controls",
           _fk("finding_id", "sw_findings", "CASCADE", nullable=False),
           sa.Column("control_type", S(20), nullable=False),
           sa.Column("description", T, nullable=False),
           sa.Column("evidence", T),
           sa.Column("reduction", sa.Float, nullable=False, server_default="0.5"),
           sa.Column("expires_at", sa.Date, nullable=False),
           sa.Column("status", S(10), nullable=False, server_default="active"),
           _fk("created_by", "users"),
           sa.Column("created_at", DT, server_default=sa.func.now()),
           _fk("revoked_by", "users"),
           sa.Column("revoked_at", DT), sa.Column("revoke_reason", T),
           sa.Column("updated_at", DT, server_default=sa.func.now()),
           indices=("finding_id", "expires_at", "status", "created_by", "revoked_by"))

    _crear("sw_exploit_events",
           sa.Column("source", S(30), nullable=False, server_default="file"),
           sa.Column("external_id", S(200), nullable=False),
           sa.Column("vuln_id", S(80)),
           _fk("ci_id", "sd_configuration_items"),
           sa.Column("host", S(255)), sa.Column("ip", S(45)),
           sa.Column("observed_at", DT, nullable=False),
           sa.Column("action", S(10), nullable=False, server_default="detected"),
           sa.Column("count", sa.Integer, nullable=False, server_default="1"),
           _fk("finding_id", "sw_findings"),
           sa.Column("details", T),
           _fk("created_by", "users"),
           sa.Column("created_at", DT, server_default=sa.func.now()),
           indices=("vuln_id", "ci_id", "observed_at", "finding_id", "created_by"),
           unicos=(("uq_sw_exploit_events_ext", ("organization_id", "source", "external_id")),))

    _crear("sw_saved_views",
           _fk("owner_user_id", "users", "CASCADE"),
           sa.Column("name", S(120), nullable=False),
           sa.Column("surface", S(15)), sa.Column("group_by", S(10)),
           sa.Column("filters", T), sa.Column("columns", T),
           sa.Column("shared", sa.Boolean, nullable=False, server_default=sa.false()),
           sa.Column("created_at", DT, server_default=sa.func.now()),
           sa.Column("updated_at", DT, server_default=sa.func.now()),
           indices=("owner_user_id",))

    _crear("sw_risk_alert_log",
           sa.Column("kind", S(20), nullable=False),
           sa.Column("alert_key", S(200), nullable=False),
           sa.Column("recipients", sa.Integer, nullable=False, server_default="0"),
           sa.Column("summary", T),
           sa.Column("sent_at", DT, server_default=sa.func.now()),
           indices=("sent_at",),
           unicos=(("uq_sw_risk_alert_log", ("organization_id", "kind", "alert_key")),))


def downgrade() -> None:
    tablas = _tablas()
    for nombre in ("sw_risk_alert_log", "sw_saved_views", "sw_exploit_events", "sw_compensating_controls",
                   "sw_risk_snapshots"):
        if nombre in tablas:
            op.drop_table(nombre)
    for tabla, columna in reversed(COLUMNAS):
        nombre = columna().name
        if tabla in _tablas() and nombre in _columnas(tabla):
            with op.batch_alter_table(tabla) as b:
                b.drop_column(nombre)
