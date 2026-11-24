"""«Del ticket al PR»: agente de código que propone un PR (23-11-2026, docs/integraciones/TICKET_A_PR.md).

Tablas nuevas (las dos con `organization_id`; la RLS la aplica `env.py` tras el
`upgrade`):

- `ticket_pr_repos`: repositorios permitidos por proyecto;
- `ticket_pr_runs`: ejecuciones (plan, build, PR, cambio vinculado, coste, log).

Índices por empresa, proyecto, ticket, tarea, repositorio, cambio, estado y
fechas, más `ix_ticket_pr_runs_org_created` (límite diario por empresa).

No hay datos que migrar: el módulo nace apagado en cada empresa (módulo
`ticket_pr` de la gobernanza de IA, sin fila = apagado) y su configuración vive en
`app_settings` (`ticket_pr.config`) y en el almacén de credenciales
(`integration_credentials`, proveedor `ticket_pr`), que ya existen.

Deshacer real: borra las dos tablas (con sus filas), la configuración
`ticket_pr.config`, las credenciales del proveedor `ticket_pr` y las filas del
módulo `ticket_pr` de la gobernanza de IA. Los PR ya abiertos en GitHub o GitLab
no se tocan (quedan en el proveedor; se listan en el log).

Compatible con SQLite y Postgres (solo `create_table`/`create_index`; sin
`ALTER` sobre tablas existentes). Idempotente: cada tabla e índice mira antes si existe.

Revision ID: 203_ticket_a_pr
Revises: 202_cuaderno
"""
import logging

import sqlalchemy as sa
from alembic import op

revision = "203_ticket_a_pr"
down_revision = "202_cuaderno"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.203")

_TZ = sa.DateTime(timezone=True)

#: Orden de creación (padres antes); el borrado va al revés.
TABLAS = ("ticket_pr_repos", "ticket_pr_runs")


def _insp():
    return sa.inspect(op.get_bind())


def _tablas() -> set:
    return set(_insp().get_table_names())


def _org():
    return sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                     nullable=True)


def _usuario(nombre: str):
    return sa.Column(nombre, sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


def _columnas() -> dict:
    """Definición de cada tabla (la misma que `app/models/ticket_a_pr.py`)."""
    return {
        "ticket_pr_repos": [
            sa.Column("id", sa.String(36), primary_key=True), _org(),
            sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
            sa.Column("provider", sa.String(20), nullable=False),
            sa.Column("repo_full_name", sa.String(256), nullable=False),
            sa.Column("default_branch", sa.String(200), nullable=False, server_default="main"),
            sa.Column("test_command", sa.String(500), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            _usuario("created_by"),
            sa.Column("created_at", _TZ, server_default=sa.func.now(), nullable=True),
            sa.Column("updated_at", _TZ, nullable=True),
        ],
        "ticket_pr_runs": [
            sa.Column("id", sa.String(36), primary_key=True), _org(),
            sa.Column("source_type", sa.String(10), nullable=False),
            sa.Column("ticket_id", sa.String(36), sa.ForeignKey("sd_tickets.id", ondelete="SET NULL"), nullable=True),
            sa.Column("task_id", sa.String(36), sa.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True),
            sa.Column("source_ref", sa.String(40), nullable=True),
            sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True),
            sa.Column("repo_id", sa.String(36), sa.ForeignKey("ticket_pr_repos.id", ondelete="SET NULL"),
                      nullable=True),
            sa.Column("provider", sa.String(20), nullable=False),
            sa.Column("repo_full_name", sa.String(256), nullable=False),
            sa.Column("base_branch", sa.String(200), nullable=False),
            sa.Column("base_sha", sa.String(64), nullable=True),
            sa.Column("branch_name", sa.String(255), nullable=True),
            sa.Column("engine", sa.String(30), nullable=False, server_default="opencode"),
            sa.Column("engine_image", sa.String(300), nullable=True),
            sa.Column("ai_provider_id", sa.String(36), sa.ForeignKey("ai_providers.id", ondelete="SET NULL"),
                      nullable=True),
            sa.Column("model", sa.String(120), nullable=True),
            sa.Column("instruction", sa.Text(), nullable=False),
            sa.Column("plan_text", sa.Text(), nullable=True),
            sa.Column("plan_files", sa.Text(), nullable=True),
            sa.Column("status", sa.String(30), nullable=False, server_default="queued_plan"),
            sa.Column("status_code", sa.String(80), nullable=True),
            sa.Column("status_params", sa.Text(), nullable=True),
            _usuario("launched_by"), _usuario("plan_decided_by"),
            sa.Column("plan_decided_at", _TZ, nullable=True),
            sa.Column("plan_decision_note", sa.String(1000), nullable=True),
            _usuario("cancelled_by"),
            sa.Column("diff_summary", sa.Text(), nullable=True),
            sa.Column("tests_ran", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("tests_passed", sa.Boolean(), nullable=True),
            sa.Column("reasoning_summary", sa.Text(), nullable=True),
            sa.Column("pr_number", sa.Integer(), nullable=True),
            sa.Column("pr_url", sa.String(1024), nullable=True),
            sa.Column("head_sha", sa.String(64), nullable=True),
            sa.Column("pr_status_state", sa.String(20), nullable=True),
            sa.Column("change_id", sa.String(36), sa.ForeignKey("sd_change_requests.id", ondelete="SET NULL"),
                      nullable=True),
            sa.Column("tokens_in", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("tokens_out", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("cost_usd", sa.Numeric(18, 6), nullable=False, server_default="0"),
            sa.Column("agent_seconds", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("log_redacted", sa.Text(), nullable=True),
            sa.Column("started_at", _TZ, nullable=True),
            sa.Column("finished_at", _TZ, nullable=True),
            sa.Column("created_at", _TZ, server_default=sa.func.now(), nullable=True),
            sa.Column("updated_at", _TZ, nullable=True),
        ],
    }


#: Índices `ix_<tabla>_<columna>` (los de `index=True` del modelo).
INDICES: dict = {
    "ticket_pr_repos": ("organization_id", "project_id", "created_by"),
    "ticket_pr_runs": ("organization_id", "ticket_id", "task_id", "project_id", "repo_id", "status",
                       "launched_by", "plan_decided_by", "cancelled_by", "change_id", "finished_at", "created_at"),
}
COMPUESTOS = {"ticket_pr_runs": (("ix_ticket_pr_runs_org_created", ("organization_id", "created_at")),)}


def upgrade() -> None:
    hay = _tablas()
    columnas = _columnas()
    for tabla in TABLAS:
        if tabla not in hay:
            op.create_table(tabla, *columnas[tabla])
        existentes = {i["name"] for i in _insp().get_indexes(tabla)}
        for col in INDICES[tabla]:
            nombre = f"ix_{tabla}_{col}"
            if nombre not in existentes:
                op.create_index(nombre, tabla, [col])
        for nombre, cols in COMPUESTOS.get(tabla, ()):
            if nombre not in existentes:
                op.create_index(nombre, tabla, list(cols))
    logger.info("203: tablas de «Del ticket al PR» listas")


def downgrade() -> None:
    bind = op.get_bind()
    hay = _tablas()
    if "ticket_pr_runs" in hay:
        n = bind.execute(sa.text("SELECT COUNT(*) FROM ticket_pr_runs WHERE pr_url IS NOT NULL")).scalar() or 0
        if n:
            logger.warning("203 (deshacer): %s PR abiertos por el agente quedan en GitHub/GitLab sin su ejecución", n)
    # Configuración, credenciales y módulo de la gobernanza del módulo (sin tabla propia).
    if "app_settings" in hay:
        bind.execute(sa.text("DELETE FROM app_settings WHERE key = 'ticket_pr.config'"))
    if "integration_credentials" in hay:
        bind.execute(sa.text("DELETE FROM integration_credentials WHERE provider = 'ticket_pr'"))
    if "ai_governance_configs" in hay:
        bind.execute(sa.text("DELETE FROM ai_governance_configs WHERE module = 'ticket_pr'"))
    for tabla in reversed(TABLAS):
        if tabla in hay:
            for i in _insp().get_indexes(tabla):
                if i["name"] and i["name"].startswith("ix_"):
                    op.drop_index(i["name"], table_name=tabla)
            op.drop_table(tabla)
