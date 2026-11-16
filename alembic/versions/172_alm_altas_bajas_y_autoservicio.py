"""Licencias y hardware — fase 4: integración (16-11-2026).

Tablas nuevas (ver `app/models/alm_integracion.py`):
  · alm_kits, alm_kit_elementos: el kit de alta por rol, puesto, departamento o
    equipo, configurable por empresa (licencias y tipos de equipo);
  · alm_propuestas_de_kit: lo propuesto al dar de alta a una persona y lo que
    pasó con cada elemento al confirmarlo;
  · alm_bajas, alm_devoluciones: el expediente de baja (licencias que se
    liberan ya o tras N días) y cada devolución de equipo con su ticket, hasta
    el acta firmada;
  · alm_items_de_catalogo, alm_peticiones: qué ítems del catálogo del service
    desk piden licencia o equipo, y cada petición con lo que se le dio.

No toca tablas existentes. Idempotente: cada tabla solo si falta.
"""
from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "172_alm_altas_bajas_y_autoservicio"
down_revision: Union[str, None] = "171_alm_uso_real"
branch_labels = None
depends_on = None

#: En orden de creación (las de después apuntan a las de antes).
TABLAS = (
    "alm_kits", "alm_kit_elementos", "alm_propuestas_de_kit", "alm_bajas", "alm_devoluciones",
    "alm_items_de_catalogo", "alm_peticiones",
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
    _crear("alm_kits",
           sa.Column("nombre", sa.String(200), nullable=False),
           sa.Column("descripcion", sa.Text(), nullable=True),
           sa.Column("criterio", sa.String(20), nullable=False, server_default="todos"),
           sa.Column("valor", sa.String(200), nullable=True),
           sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
           _fk("created_by", "users"),
           sa.Column("created_at", sa.DateTime(timezone=True), server_default=ahora),
           sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
           indices=("created_by",))

    _crear("alm_kit_elementos",
           _fk("kit_id", "alm_kits", "CASCADE", nullable=False),
           sa.Column("tipo", sa.String(10), nullable=False),
           _fk("license_id", "alm_licenses", "CASCADE"),
           sa.Column("asset_type", sa.String(20), nullable=True),
           sa.Column("cantidad", sa.Integer(), nullable=False, server_default="1"),
           sa.Column("notas", sa.String(500), nullable=True),
           indices=("kit_id", "license_id"))

    _crear("alm_propuestas_de_kit",
           _fk("user_id", "users", "CASCADE", nullable=False),
           _fk("responsable_id", "users"),
           sa.Column("estado", sa.String(15), nullable=False, server_default="pendiente"),
           sa.Column("kits", sa.Text(), nullable=True),
           sa.Column("elementos", sa.Text(), nullable=False),
           sa.Column("resultado", sa.Text(), nullable=True),
           _fk("decidida_por", "users"),
           sa.Column("decidida_en", sa.DateTime(timezone=True), nullable=True),
           sa.Column("created_at", sa.DateTime(timezone=True), server_default=ahora),
           indices=("user_id", "responsable_id", "decidida_por"))

    _crear("alm_bajas",
           _fk("user_id", "users", "CASCADE", nullable=False),
           sa.Column("motivo", sa.String(15), nullable=False),
           sa.Column("estado", sa.String(25), nullable=False, server_default="pendiente_devolucion"),
           sa.Column("fecha_efectiva", sa.Date(), nullable=False),
           sa.Column("licencias_liberar_en", sa.Date(), nullable=True),
           sa.Column("licencias_liberadas_en", sa.DateTime(timezone=True), nullable=True),
           sa.Column("licencias_liberadas", sa.Integer(), nullable=False, server_default="0"),
           sa.Column("confirmada_con_pendientes", sa.Boolean(), nullable=False, server_default=sa.false()),
           sa.Column("notas", sa.Text(), nullable=True),
           _fk("creada_por", "users"),
           sa.Column("created_at", sa.DateTime(timezone=True), server_default=ahora),
           sa.Column("cerrada_en", sa.DateTime(timezone=True), nullable=True),
           indices=("user_id", "creada_por"))

    _crear("alm_devoluciones",
           _fk("baja_id", "alm_bajas", "CASCADE"),
           _fk("asset_id", "alm_assets", "CASCADE", nullable=False),
           _fk("user_id", "users"),
           _fk("ticket_id", "sd_tickets"),
           sa.Column("origen", sa.String(15), nullable=False, server_default="baja"),
           sa.Column("estado", sa.String(15), nullable=False, server_default="pendiente"),
           sa.Column("fecha_limite", sa.Date(), nullable=True),
           sa.Column("acta_id", sa.String(36), nullable=True),
           sa.Column("condicion", sa.String(10), nullable=True),
           sa.Column("notas", sa.Text(), nullable=True),
           _fk("solicitada_por", "users"),
           sa.Column("created_at", sa.DateTime(timezone=True), server_default=ahora),
           sa.Column("recibida_en", sa.DateTime(timezone=True), nullable=True),
           _fk("recibida_por", "users"),
           sa.Column("cerrada_en", sa.DateTime(timezone=True), nullable=True),
           indices=("baja_id", "asset_id", "user_id", "ticket_id", "acta_id", "solicitada_por", "recibida_por"))

    _crear("alm_items_de_catalogo",
           _fk("service_item_id", "sd_service_items", "CASCADE", nullable=False),
           sa.Column("tipo", sa.String(10), nullable=False),
           _fk("license_id", "alm_licenses"),
           sa.Column("asset_type", sa.String(20), nullable=True),
           sa.Column("created_at", sa.DateTime(timezone=True), server_default=ahora),
           indices=("service_item_id", "license_id"),
           extra=(sa.UniqueConstraint("organization_id", "service_item_id", name="uq_alm_item_catalogo_org_item"),))

    _crear("alm_peticiones",
           _fk("ticket_id", "sd_tickets", "CASCADE", nullable=False),
           sa.Column("tipo", sa.String(10), nullable=False),
           _fk("beneficiario_id", "users"),
           _fk("solicitante_id", "users"),
           _fk("license_id", "alm_licenses"),
           sa.Column("asset_type", sa.String(20), nullable=True),
           _fk("project_id", "projects"),
           sa.Column("motivo", sa.Text(), nullable=True),
           sa.Column("estado", sa.String(15), nullable=False, server_default="pendiente"),
           sa.Column("asignacion_id", sa.String(36), nullable=True),
           _fk("asset_id", "alm_assets"),
           _fk("compra_ticket_id", "sd_tickets"),
           sa.Column("detalle", sa.Text(), nullable=True),
           sa.Column("created_at", sa.DateTime(timezone=True), server_default=ahora),
           sa.Column("cumplida_en", sa.DateTime(timezone=True), nullable=True),
           indices=("ticket_id", "beneficiario_id", "solicitante_id", "license_id", "project_id",
                    "asignacion_id", "asset_id", "compra_ticket_id"),
           extra=(sa.UniqueConstraint("ticket_id", name="uq_alm_peticion_ticket"),))


def downgrade() -> None:
    existentes = _tablas()
    for nombre in reversed(TABLAS):
        if nombre in existentes:
            op.drop_table(nombre)
