"""Motor comun de politicas, reglas y flujos (tarea #26).

Tablas nuevas (ver `app/models/politicas.py`):
  · politicas, politica_reglas: politicas versionadas con vigencia, ambito,
    prioridad y reglas (arbol de condiciones + resultados graduados);
  · tablas_de_referencia, tabla_de_referencia_filas: valores por pais, ciudad
    y categoria, con moneda y vigencia;
  · politica_evaluaciones: la explicacion de cada evaluacion guardada;
  · approval_request_steps: pasos que el motor anade a UNA solicitud.

Columnas nuevas en el motor de aprobaciones:
  · approval_steps.kind (approve | inform) y approver_level (N-esimo responsable);
  · approval_workflows.diagrama (el diseno grafico);
  · approval_requests.contexto (para las condiciones de rama);
  · approval_decisions.step_ref (la rama que decide en una etapa en paralelo).

Y en expenses: country y city, para las tablas por pais y ciudad.

Toda clave ajena con su indice `ix_<tabla>_<columna>`, como en la 164.
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "165_motor_de_politicas_y_flujos"
down_revision: Union[str, None] = "164_paridad_postgres_e_indices_de_claves_ajenas"
branch_labels = None
depends_on = None


def _org():
    return sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)


def _usuario(nombre):
    return sa.Column(nombre, sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


def _indices(tabla, *columnas):
    for c in columnas:
        op.create_index(f"ix_{tabla}_{c}", tabla, [c])


def upgrade() -> None:
    op.create_table(
        "politicas",
        sa.Column("id", sa.String(36), primary_key=True),
        _org(),
        sa.Column("familia_id", sa.String(36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("estado", sa.String(12), nullable=False),
        sa.Column("dominio", sa.String(40), nullable=False),
        sa.Column("nombre", sa.String(200), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("prioridad", sa.Integer(), nullable=False),
        sa.Column("activa", sa.Boolean(), nullable=False),
        sa.Column("vigente_desde", sa.Date(), nullable=True),
        sa.Column("vigente_hasta", sa.Date(), nullable=True),
        sa.Column("ambito", sa.Text(), nullable=True),
        sa.Column("nota_de_version", sa.String(500), nullable=True),
        _usuario("created_by"),
        _usuario("publicada_por"),
        sa.Column("publicada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )
    _indices("politicas", "organization_id", "familia_id", "created_by", "publicada_por")
    op.create_index("ix_politicas_org_dominio_estado", "politicas", ["organization_id", "dominio", "estado"])

    op.create_table(
        "politica_reglas",
        sa.Column("id", sa.String(36), primary_key=True),
        _org(),
        sa.Column("politica_id", sa.String(36), sa.ForeignKey("politicas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.String(200), nullable=False),
        sa.Column("activa", sa.Boolean(), nullable=False),
        sa.Column("condicion", sa.Text(), nullable=True),
        sa.Column("resultados", sa.Text(), nullable=True),
        sa.Column("exceso", sa.Text(), nullable=True),
        sa.Column("detener", sa.Boolean(), nullable=False),
    )
    _indices("politica_reglas", "organization_id", "politica_id")

    op.create_table(
        "tablas_de_referencia",
        sa.Column("id", sa.String(36), primary_key=True),
        _org(),
        sa.Column("nombre", sa.String(200), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("dominio", sa.String(40), nullable=True),
        sa.Column("tipo_de_valor", sa.String(10), nullable=False),
        sa.Column("moneda", sa.String(3), nullable=True),
        _usuario("created_by"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )
    _indices("tablas_de_referencia", "organization_id", "created_by")

    op.create_table(
        "tabla_de_referencia_filas",
        sa.Column("id", sa.String(36), primary_key=True),
        _org(),
        sa.Column("tabla_id", sa.String(36), sa.ForeignKey("tablas_de_referencia.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pais", sa.String(2), nullable=True),
        sa.Column("ciudad", sa.String(120), nullable=True),
        sa.Column("categoria", sa.String(60), nullable=True),
        sa.Column("valor", sa.Float(), nullable=False),
        sa.Column("moneda", sa.String(3), nullable=True),
        sa.Column("vigente_desde", sa.Date(), nullable=True),
        sa.Column("vigente_hasta", sa.Date(), nullable=True),
    )
    _indices("tabla_de_referencia_filas", "organization_id", "tabla_id")

    op.create_table(
        "politica_evaluaciones",
        sa.Column("id", sa.String(36), primary_key=True),
        _org(),
        sa.Column("dominio", sa.String(40), nullable=False),
        sa.Column("entidad_id", sa.String(64), nullable=False),
        sa.Column("momento", sa.String(30), nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("resultado", sa.Text(), nullable=False),
        sa.Column("explicacion", sa.Text(), nullable=False),
        sa.Column("solicitud_id", sa.String(36), sa.ForeignKey("approval_requests.id", ondelete="SET NULL"), nullable=True),
        _usuario("evaluado_por"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    _indices("politica_evaluaciones", "organization_id", "solicitud_id", "evaluado_por", "created_at")
    op.create_index("ix_politica_evaluaciones_entidad", "politica_evaluaciones", ["dominio", "entidad_id"])

    op.create_table(
        "approval_request_steps",
        sa.Column("id", sa.String(36), primary_key=True),
        _org(),
        sa.Column("request_id", sa.String(36), sa.ForeignKey("approval_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("approver_type", sa.String(30), nullable=False),
        sa.Column("approver_role", sa.String(50), nullable=True),
        _usuario("approver_user_id"),
        sa.Column("approver_department", sa.String(100), nullable=True),
        sa.Column("approver_group_id", sa.String(36), sa.ForeignKey("approval_groups.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approver_level", sa.Integer(), nullable=True),
        sa.Column("is_optional", sa.Boolean(), nullable=True),
        sa.Column("timeout_hours", sa.Integer(), nullable=True),
        sa.Column("on_timeout", sa.String(20), nullable=True),
        _usuario("escalate_to_user_id"),
        sa.Column("parallel_quorum", sa.Boolean(), nullable=True),
        sa.Column("required_approvals", sa.Integer(), nullable=True),
        sa.Column("step_condition", sa.Text(), nullable=True),
        sa.Column("requires_attachment", sa.Boolean(), nullable=True),
        sa.Column("reminder_hours", sa.Integer(), nullable=True),
        sa.Column("origen", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )
    _indices("approval_request_steps", "organization_id", "request_id", "approver_user_id",
             "approver_group_id", "escalate_to_user_id")

    op.add_column("approval_steps", sa.Column("kind", sa.String(10), nullable=False, server_default="approve"))
    op.add_column("approval_steps", sa.Column("approver_level", sa.Integer(), nullable=True))
    op.add_column("approval_workflows", sa.Column("diagrama", sa.Text(), nullable=True))
    op.add_column("approval_requests", sa.Column("contexto", sa.Text(), nullable=True))
    op.add_column("approval_decisions", sa.Column("step_ref", sa.String(36), nullable=True))
    op.add_column("expenses", sa.Column("country", sa.String(2), nullable=True))
    op.add_column("expenses", sa.Column("city", sa.String(120), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("expenses") as b:
        b.drop_column("city")
        b.drop_column("country")
    with op.batch_alter_table("approval_decisions") as b:
        b.drop_column("step_ref")
    with op.batch_alter_table("approval_requests") as b:
        b.drop_column("contexto")
    with op.batch_alter_table("approval_workflows") as b:
        b.drop_column("diagrama")
    with op.batch_alter_table("approval_steps") as b:
        b.drop_column("approver_level")
        b.drop_column("kind")
    for tabla in ("approval_request_steps", "politica_evaluaciones", "tabla_de_referencia_filas",
                  "tablas_de_referencia", "politica_reglas", "politicas"):
        op.drop_table(tabla)
