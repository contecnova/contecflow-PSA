"""Clientes internos (rev. 193): cargos, repartos, beneficios y adopción.

El cliente interno es un `Client` con `kind="interno"` (app/models/clients.py).
Aquí solo lo que no existía: ver docs/CLIENTES_INTERNOS.md.
"""
import uuid

from sqlalchemy import (Boolean, Column, Date, DateTime, Float, ForeignKey, Integer,
                        String, Text, UniqueConstraint)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base
from app.models.money import Money, Rate


def _id() -> str:
    return str(uuid.uuid4())


KINDS = ("externo", "interno")
INTERNAL_TYPES = ("departamento", "unidad_negocio", "filial", "centro_coste")
FINANCE_MODES = ("showback", "chargeback", "intercompania")
COST_METHODS = ("horas_coste", "tarifa_interna", "precio_cerrado", "catalogo")
ROLES = ("usuario_clave", "finanzas", "delegado")
CRITERIOS_REPARTO = ("usuarios", "tickets", "licencias", "software", "fijo")
ESTADOS_CARGO = ("borrador", "emitido", "exportado", "anulado")
TIPOS_BENEFICIO = ("ahorro", "ingreso", "riesgo", "intangible")
TIPOS_ADOPCION = ("formacion", "comunicacion", "soporte", "hito")
ESTADOS_ADOPCION = ("pendiente", "en_curso", "hecho")


class InternalClientRole(Base):
    """Designación explícita en una unidad interna (usuario clave, finanzas, delegado).

    Los usuarios de la unidad no se dan de alta: se deducen de RR. HH.
    (`users.department`, centro de coste). Esto solo marca papeles concretos.
    """
    __tablename__ = "internal_client_roles"
    __table_args__ = (UniqueConstraint("client_id", "user_id", "role", name="uq_internal_client_role"),)

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    client_id = Column(String(36), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(20), nullable=False)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class InternalSharedCost(Base):
    """Servicio compartido cuyo coste mensual se reparte entre unidades por un criterio."""
    __tablename__ = "internal_shared_costs"

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    monthly_amount = Column(Money, nullable=False, default=0, server_default="0")
    currency = Column(String(3), nullable=True)
    criterion = Column(String(15), nullable=False, default="usuarios", server_default="usuarios")
    fixed_shares = Column(Text, nullable=False, default="{}", server_default="{}")  # {"client_id": pct} si criterio fijo
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class InternalCharge(Base):
    """Informe de showback, nota de cargo interna o cargo intercompañía de un mes.

    La nota de cargo NO es una factura: sin IVA, sin serie legal; se exporta al
    ERP como asiento entre centros de coste. La intercompañía sí enlaza una
    factura real (`invoice_id`) hecha con la facturación de siempre.
    """
    __tablename__ = "internal_charges"
    __table_args__ = (UniqueConstraint("organization_id", "number", name="uq_internal_charge_number"),)

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    client_id = Column(String(36), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(30), nullable=False)
    period = Column(String(7), nullable=False, index=True)
    mode = Column(String(15), nullable=False)
    status = Column(String(15), nullable=False, default="borrador", server_default="borrador", index=True)
    total = Column(Money, nullable=False, default=0, server_default="0")
    currency = Column(String(3), nullable=True)
    invoice_id = Column(String(36), ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True, index=True)
    erp_reference = Column(String(80), nullable=True)
    notes = Column(Text, nullable=True)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    issued_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    issued_at = Column(DateTime(timezone=True), nullable=True)
    exported_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    lines = relationship("InternalChargeLine", back_populates="charge",
                         cascade="all, delete-orphan", order_by="InternalChargeLine.source")


class InternalChargeLine(Base):
    __tablename__ = "internal_charge_lines"

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    charge_id = Column(String(36), ForeignKey("internal_charges.id", ondelete="CASCADE"), nullable=False, index=True)
    source = Column(String(20), nullable=False)      # horas | precio_cerrado | catalogo | reparto | licencias | activos | software
    source_ref = Column(String(36), nullable=True)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    description = Column(String(500), nullable=False)
    quantity = Column(Float, nullable=True)
    unit_amount = Column(Rate, nullable=True)
    amount = Column(Money, nullable=False, default=0, server_default="0")

    charge = relationship("InternalCharge", back_populates="lines")


class ProjectBenefit(Base):
    """Beneficio esperado de un proyecto (caso de negocio) y su seguimiento."""
    __tablename__ = "project_benefits"

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    kind = Column(String(15), nullable=False, default="ahorro", server_default="ahorro")
    unit = Column(String(30), nullable=True)
    baseline = Column(Float, nullable=True)
    target = Column(Float, nullable=True)
    actual = Column(Float, nullable=True)
    target_date = Column(Date, nullable=True)
    measured_at = Column(Date, nullable=True)
    owner_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class InternalAdoptionItem(Base):
    """Acción del plan de adopción y formación de una unidad (opcionalmente de un proyecto)."""
    __tablename__ = "internal_adoption_items"

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    client_id = Column(String(36), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    course_id = Column(String(36), ForeignKey("training_courses.id", ondelete="SET NULL"), nullable=True)
    kind = Column(String(15), nullable=False, default="formacion", server_default="formacion")
    title = Column(String(200), nullable=False)
    due_date = Column(Date, nullable=True)
    status = Column(String(15), nullable=False, default="pendiente", server_default="pendiente")
    target_users = Column(Integer, nullable=True)
    reached_users = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
