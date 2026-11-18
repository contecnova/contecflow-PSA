"""Horas extra y trabajo fuera de horario aprobados por flujos (18-11-2026).

Tablas nuevas (ver `app/models/horas_extra.py`): `config_horas_extra`,
`peticiones_de_horas_extra`, `eventos_de_horas_extra` y
`presupuestos_de_horas_extra`. No se crea ninguna configuración: sin fila, el
módulo está desactivado y la imputación se comporta como antes.

Idempotente: cada tabla se crea solo si no existe. La política RLS de cada
tabla la aplica `env.py` en cada `upgrade` (`app/db/rls.py`).

Downgrade: borra las cuatro tablas (con sus datos).

Revision ID: 184_horas_extra
Revises: 183_contacto_principal_correlacionado
"""
import sqlalchemy as sa
from alembic import op

revision = "184_horas_extra"
down_revision = "183_contacto_principal_correlacionado"
branch_labels = None
depends_on = None


def _tablas() -> set:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _org():
    return sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                     nullable=True)


def _usuario(nombre, nullable=True, ondelete="SET NULL"):
    return sa.Column(nombre, sa.String(36), sa.ForeignKey("users.id", ondelete=ondelete), nullable=nullable)


def _crear(nombre, *columnas, indices=(), extra=()):
    if nombre in _tablas():
        return
    op.create_table(nombre, sa.Column("id", sa.String(36), primary_key=True), _org(), *columnas, *extra)
    for c in ("organization_id", *indices):
        op.create_index(f"ix_{nombre}_{c}", nombre, [c])


def upgrade() -> None:
    ahora = sa.func.now()
    _crear("config_horas_extra",
           sa.Column("activo", sa.Boolean(), nullable=False),
           sa.Column("control_imputacion", sa.String(12), nullable=False),
           sa.Column("tolerancia_minutos", sa.Integer(), nullable=False),
           sa.Column("compensaciones", sa.Text(), nullable=True),
           sa.Column("compensacion_por_defecto", sa.String(10), nullable=False),
           sa.Column("workflow_id", sa.String(36), sa.ForeignKey("approval_workflows.id", ondelete="SET NULL"),
                     nullable=True),
           sa.Column("tipo_bolsa_id", sa.String(36), sa.ForeignKey("tipos_de_ausencia.id", ondelete="SET NULL"),
                     nullable=True),
           sa.Column("pedir_en_nombre", sa.Boolean(), nullable=False),
           sa.Column("exigir_motivo", sa.Boolean(), nullable=False),
           _usuario("updated_by"),
           sa.Column("created_at", sa.DateTime(timezone=True), server_default=ahora, nullable=True),
           sa.Column("updated_at", sa.DateTime(timezone=True), server_default=ahora, nullable=True),
           indices=("workflow_id", "tipo_bolsa_id", "updated_by"),
           extra=(sa.UniqueConstraint("organization_id", name="uq_config_horas_extra_org"),))
    _crear("peticiones_de_horas_extra",
           _usuario("user_id", nullable=False, ondelete="CASCADE"),
           _usuario("solicitante_id"),
           sa.Column("origen", sa.String(10), nullable=False),
           sa.Column("tipo", sa.String(16), nullable=False),
           sa.Column("clase_dia", sa.String(14), nullable=True),
           sa.Column("fecha", sa.Date(), nullable=False),
           sa.Column("hora_inicio", sa.Time(), nullable=True),
           sa.Column("hora_fin", sa.Time(), nullable=True),
           sa.Column("horas", sa.Float(), nullable=False),
           sa.Column("horas_autorizadas", sa.Float(), nullable=True),
           sa.Column("motivo", sa.Text(), nullable=True),
           sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True),
           sa.Column("ticket_id", sa.String(36), nullable=True),
           _usuario("sustituto_id"),
           sa.Column("compensacion", sa.String(10), nullable=False),
           sa.Column("factor", sa.Float(), nullable=False),
           sa.Column("estado", sa.String(12), nullable=False),
           sa.Column("avisos", sa.Text(), nullable=True),
           _usuario("decidido_por"),
           sa.Column("decidido_en", sa.DateTime(timezone=True), nullable=True),
           sa.Column("motivo_rechazo", sa.String(500), nullable=True),
           sa.Column("liquidada_en", sa.DateTime(timezone=True), nullable=True),
           _usuario("liquidada_por"),
           sa.Column("referencia_pago", sa.String(120), nullable=True),
           sa.Column("created_at", sa.DateTime(timezone=True), server_default=ahora, nullable=True),
           sa.Column("updated_at", sa.DateTime(timezone=True), server_default=ahora, nullable=True),
           indices=("user_id", "solicitante_id", "fecha", "project_id", "sustituto_id", "estado", "decidido_por",
                    "liquidada_por", "created_at"))
    _crear("eventos_de_horas_extra",
           sa.Column("peticion_id", sa.String(36),
                     sa.ForeignKey("peticiones_de_horas_extra.id", ondelete="CASCADE"), nullable=False),
           sa.Column("tipo", sa.String(30), nullable=False),
           _usuario("actor_id"),
           sa.Column("datos", sa.Text(), nullable=True),
           sa.Column("created_at", sa.DateTime(timezone=True), server_default=ahora, nullable=True),
           indices=("peticion_id", "actor_id", "created_at"))
    _crear("presupuestos_de_horas_extra",
           sa.Column("ambito", sa.String(14), nullable=False),
           sa.Column("valor", sa.String(160), nullable=True),
           sa.Column("periodo", sa.String(6), nullable=False),
           sa.Column("anio", sa.Integer(), nullable=True),
           sa.Column("horas", sa.Float(), nullable=False),
           sa.Column("nota", sa.String(255), nullable=True),
           sa.Column("activo", sa.Boolean(), nullable=False),
           _usuario("created_by"),
           sa.Column("created_at", sa.DateTime(timezone=True), server_default=ahora, nullable=True),
           sa.Column("updated_at", sa.DateTime(timezone=True), server_default=ahora, nullable=True),
           indices=("created_by",))


def downgrade() -> None:
    for t in ("eventos_de_horas_extra", "presupuestos_de_horas_extra", "peticiones_de_horas_extra",
              "config_horas_extra"):
        if t in _tablas():
            op.drop_table(t)
