"""Catálogo de cambios estándar, cambio de contraseña del portal y preferencias de reuniones (23-11-2026).

Segunda ronda de la auditoría 2026-11-22 (docs/auditoria/2026-11-22/):

1. `sd_standard_change_models` (A-SD19): catálogo por empresa de modelos de
   cambio estándar preaprobados por el CAB (ITIL 4). Un cambio solo es
   `standard` si referencia un modelo aprobado, vigente y cuyo alcance cubre
   el cambio; antes bastaba con que el solicitante declarase el tipo.
   - `sd_change_requests.standard_model_id` → `sd_standard_change_models.id`
     (ON DELETE SET NULL), con índice. Los cambios existentes quedan sin
     modelo: los `standard` que aún no se han aprobado irán al CAB al
     enviarse (el servidor fija el tipo).
2. `client_users.must_change_password` Boolean NOT NULL, por defecto false: el
   portal obliga a cambiar la contraseña generada por el sistema (alta y
   «Reenviar acceso») antes de usar el resto de rutas. Las filas existentes
   quedan en false (no se bloquea a nadie que ya entra).
3. `ai_meeting_user_prefs`: la única `uq_ai_meeting_user_prefs_user`
   (user_id) pasa a `uq_ai_meeting_user_prefs_org_user` (organization_id,
   user_id): una persona de varias empresas tiene preferencias en cada una (la
   global daba 500 al guardar en la segunda).

SQLite: `batch_alter_table` (recrea la tabla) para la clave ajena y las únicas.
PostgreSQL: ALTER directos. La RLS de la tabla nueva la aplica `env.py` tras el
`upgrade` (tiene `organization_id`).

Deshacer real: borra la tabla y las columnas, y vuelve a la única por persona
(falla si para entonces hay una persona con preferencias en dos empresas: hay
que decidir cuál se queda antes de bajar).

Idempotente: cada paso mira antes si ya está hecho.

Revision ID: 198_cambios_estandar_y_portal
Revises: 197_dinero_numeric
"""
import sqlalchemy as sa
from alembic import op

revision = "198_cambios_estandar_y_portal"
down_revision = "197_dinero_numeric"
branch_labels = None
depends_on = None

_TZ = sa.DateTime(timezone=True)
MODELOS = "sd_standard_change_models"
CAMBIOS = "sd_change_requests"
FK_MODELO = "fk_sd_change_requests_standard_model_id"
IX_MODELO = "ix_sd_change_requests_standard_model_id"
PREFS = "ai_meeting_user_prefs"
UQ_PREFS_ANTES = "uq_ai_meeting_user_prefs_user"
UQ_PREFS_AHORA = "uq_ai_meeting_user_prefs_org_user"


def _insp():
    return sa.inspect(op.get_bind())


def _tablas() -> set:
    return set(_insp().get_table_names())


def _columnas(tabla: str) -> set:
    return {c["name"] for c in _insp().get_columns(tabla)}


def _unicas(tabla: str) -> set:
    return {u["name"] for u in _insp().get_unique_constraints(tabla) if u.get("name")}


def _sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


# ── 1. catálogo de cambios estándar ──────────────────────────────────────────

def _crear_modelos() -> None:
    if MODELOS in _tablas():
        return
    op.create_table(
        MODELOS,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("procedure", sa.Text(), nullable=False),
        sa.Column("rollback_plan", sa.Text(), nullable=True),
        sa.Column("test_plan", sa.Text(), nullable=True),
        sa.Column("max_risk", sa.String(20), nullable=False, server_default="low"),
        sa.Column("applies_to_ci_ids", sa.Text(), nullable=True),
        sa.Column("applies_to_ci_types", sa.Text(), nullable=True),
        sa.Column("applies_to_service_ids", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="proposed"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("proposed_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_at", _TZ, nullable=True),
        sa.Column("review_interval_days", sa.Integer(), nullable=True),
        sa.Column("next_review_at", _TZ, nullable=True),
        sa.Column("suspended_at", _TZ, nullable=True),
        sa.Column("suspended_reason", sa.Text(), nullable=True),
        sa.Column("use_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", _TZ, server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", _TZ, nullable=True),
    )
    for col in ("organization_id", "proposed_by", "approved_by", "next_review_at"):
        op.create_index(f"ix_{MODELOS}_{col}", MODELOS, [col])
    op.create_index(f"ix_{MODELOS}_org_status", MODELOS, ["organization_id", "status"])


def _anadir_modelo_a_cambios() -> None:
    if "standard_model_id" in _columnas(CAMBIOS):
        return
    with op.batch_alter_table(CAMBIOS) as b:
        b.add_column(sa.Column("standard_model_id", sa.String(36), nullable=True))
        b.create_foreign_key(FK_MODELO, MODELOS, ["standard_model_id"], ["id"], ondelete="SET NULL")
        b.create_index(IX_MODELO, ["standard_model_id"])


# ── 2. portal: cambio de contraseña obligatorio ──────────────────────────────

def _anadir_must_change_password() -> None:
    if "must_change_password" in _columnas("client_users"):
        return
    with op.batch_alter_table("client_users") as b:
        b.add_column(sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.false()))


# ── 3. preferencias de reuniones: única por empresa ──────────────────────────

def _unica_de_prefs(quitar: str, poner: str, columnas: list) -> None:
    if PREFS not in _tablas():
        return
    hay = _unicas(PREFS)
    if poner in hay and quitar not in hay:
        return
    with op.batch_alter_table(PREFS) as b:
        if quitar in hay:
            b.drop_constraint(quitar, type_="unique")
        if poner not in hay:
            b.create_unique_constraint(poner, columnas)


def upgrade() -> None:
    _crear_modelos()
    _anadir_modelo_a_cambios()
    _anadir_must_change_password()
    _unica_de_prefs(UQ_PREFS_ANTES, UQ_PREFS_AHORA, ["organization_id", "user_id"])


def downgrade() -> None:
    _unica_de_prefs(UQ_PREFS_AHORA, UQ_PREFS_ANTES, ["user_id"])
    if "must_change_password" in _columnas("client_users"):
        with op.batch_alter_table("client_users") as b:
            b.drop_column("must_change_password")
    if "standard_model_id" in _columnas(CAMBIOS):
        with op.batch_alter_table(CAMBIOS) as b:
            b.drop_index(IX_MODELO)
            b.drop_constraint(FK_MODELO, type_="foreignkey")
            b.drop_column("standard_model_id")
    if MODELOS in _tablas():
        op.drop_table(MODELOS)
