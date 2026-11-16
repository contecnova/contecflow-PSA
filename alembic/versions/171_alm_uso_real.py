"""Licencias y hardware — fase 2: uso real (16-11-2026).

Tablas nuevas (ver `app/models/alm_uso.py`):
  · alm_uso_conexiones, alm_uso_sincronizaciones: fuentes de uso por empresa y
    cada lectura con lo leído y sus errores (las credenciales van cifradas en
    `integration_credentials`, proveedores `alm_*`);
  · alm_uso_evidencias: una por (fuente, titular, producto), con último uso,
    frecuencia, fiabilidad y fecha de lectura;
  · alm_uso_mapeos, alm_uso_derechos: producto de la fuente → licencia y lo
    comprado según el fabricante (el pico de concurrentes va a
    `alm_picos_concurrencia`, de la 170);
  · alm_uso_niveles, alm_uso_ajustes: reglas y decisiones de ajuste de nivel;
  · alm_uso_recuperaciones: recuperación escalonada de asignaciones sin uso;
  · alm_software_no_controlado: candidatos detectados fuera de ALM.

No toca tablas existentes. Idempotente: cada tabla solo si falta.
"""
from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "171_alm_uso_real"
down_revision: Union[str, None] = "170_alm_titulares_ciclo_y_costes"
branch_labels = None
depends_on = None

#: En orden de creación (las de después apuntan a las de antes).
TABLAS = (
    "alm_uso_conexiones", "alm_uso_sincronizaciones", "alm_uso_evidencias", "alm_uso_mapeos", "alm_uso_derechos",
    "alm_uso_niveles", "alm_uso_ajustes", "alm_uso_recuperaciones", "alm_software_no_controlado",
)


def _tablas() -> set:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _org():
    return sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                     nullable=True)


def _fk(nombre, tabla, ondelete="SET NULL", nullable=True):
    return sa.Column(nombre, sa.String(36), sa.ForeignKey(f"{tabla}.id", ondelete=ondelete), nullable=nullable)


def _crear(nombre, *columnas, indices=(), extra=()):
    if nombre in _tablas():
        return
    op.create_table(nombre, sa.Column("id", sa.String(36), primary_key=True), _org(), *columnas, *extra)
    for c in ("organization_id", *indices):
        op.create_index(f"ix_{nombre}_{c}", nombre, [c])


def upgrade() -> None:
    ahora = sa.func.now()
    _crear("alm_uso_conexiones",
           sa.Column("proveedor", sa.String(30), nullable=False),
           sa.Column("activa", sa.Boolean(), nullable=False, server_default=sa.true()),
           sa.Column("fiabilidad", sa.String(10), nullable=True),
           sa.Column("configuracion", sa.Text(), nullable=True),
           sa.Column("ultima_sincronizacion_at", sa.DateTime(timezone=True), nullable=True),
           sa.Column("ultimo_estado", sa.String(20), nullable=False, server_default="nunca"),
           sa.Column("ultimo_error", sa.Text(), nullable=True),
           _fk("created_by", "users"),
           sa.Column("created_at", sa.DateTime(timezone=True), server_default=ahora),
           sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
           indices=("created_by",),
           extra=(sa.UniqueConstraint("organization_id", "proveedor", name="uq_alm_uso_conexion_org_proveedor"),))

    _crear("alm_uso_sincronizaciones",
           _fk("conexion_id", "alm_uso_conexiones", "CASCADE", nullable=False),
           sa.Column("proveedor", sa.String(30), nullable=False),
           sa.Column("origen", sa.String(15), nullable=False, server_default="programada"),
           sa.Column("estado", sa.String(15), nullable=False, server_default="en_curso"),
           sa.Column("iniciada_at", sa.DateTime(timezone=True), server_default=ahora),
           sa.Column("terminada_at", sa.DateTime(timezone=True), nullable=True),
           sa.Column("leidos", sa.Integer(), nullable=False, server_default="0"),
           sa.Column("nuevas", sa.Integer(), nullable=False, server_default="0"),
           sa.Column("actualizadas", sa.Integer(), nullable=False, server_default="0"),
           sa.Column("sin_titular", sa.Integer(), nullable=False, server_default="0"),
           sa.Column("sin_licencia", sa.Integer(), nullable=False, server_default="0"),
           sa.Column("dispositivos", sa.Integer(), nullable=False, server_default="0"),
           sa.Column("errores", sa.Text(), nullable=True),
           sa.Column("avisos", sa.Text(), nullable=True),
           _fk("iniciada_por", "users"),
           indices=("conexion_id", "iniciada_por"))
    if "ix_alm_uso_sinc_conexion_inicio" not in {i["name"] for i in sa.inspect(op.get_bind()).get_indexes(
            "alm_uso_sincronizaciones")}:
        op.create_index("ix_alm_uso_sinc_conexion_inicio", "alm_uso_sincronizaciones", ["conexion_id", "iniciada_at"])

    if "alm_uso_evidencias" not in _tablas():
        _crear("alm_uso_evidencias",
               _fk("conexion_id", "alm_uso_conexiones", "CASCADE"),
               sa.Column("fuente", sa.String(30), nullable=False),
               sa.Column("titular_tipo", sa.String(12), nullable=False),
               sa.Column("titular_externo", sa.String(320), nullable=False),
               _fk("user_id", "users"),
               _fk("asset_id", "alm_assets"),
               sa.Column("producto", sa.String(255), nullable=False),
               sa.Column("nombre_producto", sa.String(255), nullable=True),
               sa.Column("sku", sa.String(120), nullable=True),
               _fk("license_id", "alm_licenses"),
               _fk("assignment_id", "alm_license_assignments"),
               _fk("install_id", "alm_software_installs"),
               sa.Column("asignada_en_fuente", sa.Boolean(), nullable=True),
               sa.Column("ultimo_uso_at", sa.DateTime(timezone=True), nullable=True),
               sa.Column("frecuencia", sa.Integer(), nullable=True),
               sa.Column("periodo_dias", sa.Integer(), nullable=True),
               sa.Column("servicios", sa.Text(), nullable=True),
               sa.Column("fiabilidad", sa.String(10), nullable=False, server_default="media"),
               sa.Column("leido_at", sa.DateTime(timezone=True), nullable=False),
               sa.Column("vista_en_ultima_lectura", sa.Boolean(), nullable=False, server_default=sa.true()),
               sa.Column("detalle", sa.Text(), nullable=True),
               sa.Column("created_at", sa.DateTime(timezone=True), server_default=ahora),
               indices=("conexion_id", "user_id", "asset_id", "license_id", "assignment_id"),
               extra=(sa.UniqueConstraint("organization_id", "fuente", "titular_tipo", "titular_externo", "producto",
                                          name="uq_alm_uso_evidencia"),))
        op.create_index("ix_alm_uso_evidencia_licencia_usuario", "alm_uso_evidencias", ["license_id", "user_id"])
        op.create_index("ix_alm_uso_evidencia_licencia_activo", "alm_uso_evidencias", ["license_id", "asset_id"])

    _crear("alm_uso_mapeos",
           sa.Column("fuente", sa.String(30), nullable=False),
           sa.Column("producto", sa.String(255), nullable=False),
           _fk("license_id", "alm_licenses", "CASCADE"),
           sa.Column("ignorar", sa.Boolean(), nullable=False, server_default=sa.false()),
           _fk("created_by", "users"),
           sa.Column("created_at", sa.DateTime(timezone=True), server_default=ahora),
           indices=("license_id", "created_by"),
           extra=(sa.UniqueConstraint("organization_id", "fuente", "producto", name="uq_alm_uso_mapeo"),))

    _crear("alm_uso_derechos",
           _fk("conexion_id", "alm_uso_conexiones", "CASCADE"),
           sa.Column("fuente", sa.String(30), nullable=False),
           sa.Column("sku", sa.String(255), nullable=False),
           sa.Column("nombre", sa.String(255), nullable=True),
           sa.Column("comprados", sa.Integer(), nullable=True),
           sa.Column("consumidos", sa.Integer(), nullable=True),
           sa.Column("suspendidos", sa.Integer(), nullable=True),
           _fk("license_id", "alm_licenses"),
           sa.Column("detalle", sa.Text(), nullable=True),
           sa.Column("leido_at", sa.DateTime(timezone=True), nullable=False),
           indices=("conexion_id", "license_id"),
           extra=(sa.UniqueConstraint("organization_id", "fuente", "sku", name="uq_alm_uso_derecho"),))

    _crear("alm_uso_niveles",
           _fk("license_superior_id", "alm_licenses", "CASCADE", nullable=False),
           _fk("license_inferior_id", "alm_licenses", "CASCADE", nullable=False),
           sa.Column("servicios", sa.Text(), nullable=False),
           sa.Column("activa", sa.Boolean(), nullable=False, server_default=sa.true()),
           sa.Column("notas", sa.String(500), nullable=True),
           _fk("created_by", "users"),
           sa.Column("created_at", sa.DateTime(timezone=True), server_default=ahora),
           indices=("license_superior_id", "license_inferior_id", "created_by"),
           extra=(sa.UniqueConstraint("organization_id", "license_superior_id", "license_inferior_id",
                                      name="uq_alm_uso_nivel"),))

    _crear("alm_uso_ajustes",
           _fk("nivel_id", "alm_uso_niveles", "CASCADE", nullable=False),
           _fk("assignment_id", "alm_license_assignments", "CASCADE", nullable=False),
           sa.Column("decision", sa.String(15), nullable=False),
           _fk("nueva_asignacion_id", "alm_license_assignments"),
           sa.Column("ahorro_estimado", sa.Float(), nullable=True),
           sa.Column("motivo", sa.String(500), nullable=True),
           _fk("decidido_por", "users"),
           sa.Column("decidido_at", sa.DateTime(timezone=True), server_default=ahora),
           indices=("nivel_id", "assignment_id", "decidido_por"),
           extra=(sa.UniqueConstraint("organization_id", "nivel_id", "assignment_id", name="uq_alm_uso_ajuste"),))

    if "alm_uso_recuperaciones" not in _tablas():
        _crear("alm_uso_recuperaciones",
               _fk("assignment_id", "alm_license_assignments", "CASCADE", nullable=False),
               _fk("license_id", "alm_licenses", "CASCADE", nullable=False),
               _fk("user_id", "users"),
               _fk("asset_id", "alm_assets"),
               sa.Column("estado", sa.String(25), nullable=False, server_default="aviso_persona"),
               sa.Column("politica_id", sa.String(36), nullable=True),
               sa.Column("politica", sa.String(255), nullable=True),
               sa.Column("parametros", sa.Text(), nullable=True),
               sa.Column("dias_sin_uso", sa.Integer(), nullable=True),
               sa.Column("coste_anual", sa.Float(), nullable=True),
               sa.Column("iniciada_at", sa.DateTime(timezone=True), server_default=ahora),
               sa.Column("ultimo_paso_at", sa.DateTime(timezone=True), nullable=True),
               sa.Column("siguiente_paso_at", sa.DateTime(timezone=True), nullable=True),
               sa.Column("conservar_hasta", sa.Date(), nullable=True),
               sa.Column("cerrada_at", sa.DateTime(timezone=True), nullable=True),
               _fk("cerrada_por", "users"),
               sa.Column("motivo", sa.String(500), nullable=True),
               sa.Column("historial", sa.Text(), nullable=True),
               indices=("assignment_id", "license_id", "user_id", "asset_id", "estado", "cerrada_por"))
        op.create_index("ix_alm_uso_recup_asignacion_estado", "alm_uso_recuperaciones", ["assignment_id", "estado"])

    _crear("alm_software_no_controlado",
           sa.Column("clave", sa.String(255), nullable=False),
           sa.Column("nombre", sa.String(255), nullable=False),
           sa.Column("origenes", sa.Text(), nullable=True),
           sa.Column("usuarios", sa.Integer(), nullable=False, server_default="0"),
           sa.Column("dispositivos", sa.Integer(), nullable=False, server_default="0"),
           sa.Column("importe", sa.Float(), nullable=True),
           sa.Column("moneda", sa.String(3), nullable=True),
           sa.Column("primera_vez", sa.Date(), nullable=True),
           sa.Column("ultima_vez", sa.Date(), nullable=True),
           sa.Column("referencias", sa.Text(), nullable=True),
           sa.Column("estado", sa.String(15), nullable=False, server_default="nuevo"),
           _fk("license_id", "alm_licenses"),
           _fk("revisado_por", "users"),
           sa.Column("revisado_at", sa.DateTime(timezone=True), nullable=True),
           sa.Column("created_at", sa.DateTime(timezone=True), server_default=ahora),
           sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
           indices=("license_id", "revisado_por"),
           extra=(sa.UniqueConstraint("organization_id", "clave", name="uq_alm_software_no_controlado"),))


def downgrade() -> None:
    existentes = _tablas()
    for nombre in reversed(TABLAS):
        if nombre in existentes:
            op.drop_table(nombre)
