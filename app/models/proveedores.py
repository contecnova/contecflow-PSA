"""Proveedores y externalizacion (19-11-2026, migracion 189).

Ver `docs/PROVEEDORES_Y_EXTERNALIZACION.md` y `app/services/proveedores/`.

El proveedor sigue siendo `subcontractors` (con `kind`, modos y GRC nuevos).
Aqui viven sus contratos y precios, servicios gestionados, paquetes de trabajo
externalizados, informes, consumo, estados de cuenta y su GRC de terceros.
Los catalogos editables (tipos de servicio, unidades de cobro) estan en
`app/models/settings.py`, con los demas catalogos de clave.
"""
from __future__ import annotations

import uuid

from sqlalchemy import JSON, Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base
from app.models.money import Money, Rate


def _id() -> str:
    return str(uuid.uuid4())


class SupplierContract(Base):
    """Contrato con un proveedor (o plantilla, `is_template`)."""
    __tablename__ = "supplier_contracts"

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    subcontractor_id = Column(String(36), ForeignKey("subcontractors.id", ondelete="CASCADE"), nullable=True, index=True)
    is_template = Column(Boolean, default=False, nullable=False, server_default="0")
    code = Column(String(30), nullable=True)
    title = Column(String(255), nullable=False)
    contract_type = Column(String(20), nullable=False, default="framework")  # msa|sow|service|framework|freelance
    modes = Column(JSON, nullable=True)            # ["staff_augmentation", "outsourcing", "managed_services"]
    status = Column(String(20), nullable=False, default="draft")  # draft|active|suspended|expired|terminated
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    auto_renew = Column(Boolean, default=False, nullable=False, server_default="0")
    notice_days = Column(Integer, nullable=True)
    currency = Column(String(3), nullable=True)
    committed_minimum = Column(Float, nullable=True)          # minimo comprometido por periodo
    minimum_period = Column(String(20), nullable=True)        # monthly|quarterly|annual
    total_cap = Column(Money, nullable=True)                  # tope total del contrato
    po_number = Column(String(100), nullable=True)
    po_amount = Column(Money, nullable=True)
    budget_id = Column(String(36), ForeignKey("budgets.id", ondelete="SET NULL"), nullable=True, index=True)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    cost_center_id = Column(String(36), ForeignKey("alm_cost_centers.id", ondelete="SET NULL"), nullable=True, index=True)
    payment_terms_days = Column(Integer, nullable=True)
    expenses_rebillable = Column(Boolean, default=False, nullable=False, server_default="0")
    expenses_cap = Column(Float, nullable=True)
    internal_owner_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    document_url = Column(String(1000), nullable=True)
    notes = Column(Text, nullable=True)
    terminated_at = Column(Date, nullable=True)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    subcontractor = relationship("Subcontractor")
    lines = relationship("SupplierPricingLine", back_populates="contract", cascade="all, delete-orphan")


class SupplierPricingLine(Base):
    """Linea de precio de un contrato. Varias por contrato (modelos combinables)."""
    __tablename__ = "supplier_pricing_lines"

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    contract_id = Column(String(36), ForeignKey("supplier_contracts.id", ondelete="CASCADE"), nullable=False, index=True)
    model = Column(String(20), nullable=False)       # per_resource|fixed_price|per_unit|subscription|expense|bonus
    unit = Column(String(50), nullable=True)         # clave de `custom_supplier_billing_units`
    description = Column(String(255), nullable=True)
    rate_id = Column(String(36), ForeignKey("subcontractor_rates.id", ondelete="SET NULL"), nullable=True, index=True)
    service_id = Column(String(36), ForeignKey("supplier_services.id", ondelete="SET NULL"), nullable=True, index=True)
    work_package_id = Column(String(36), ForeignKey("supplier_work_packages.id", ondelete="SET NULL"), nullable=True, index=True)
    unit_price = Column(Rate, nullable=True)
    period = Column(String(20), nullable=True)       # monthly|quarterly|annual|one_time
    included_units = Column(Float, nullable=True)
    overage_price = Column(Rate, nullable=True)
    tiers = Column(JSON, nullable=True)              # [{"from": 0, "to": 100, "price": 10}, ...]
    min_amount = Column(Money, nullable=True)        # minimo por periodo
    max_amount = Column(Money, nullable=True)        # tope por periodo
    valid_from = Column(Date, nullable=True)
    valid_until = Column(Date, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False, server_default="1")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    contract = relationship("SupplierContract", back_populates="lines")
    rate = relationship("SubcontractorRate")


class SupplierService(Base):
    """Servicio gestionado contratado (SOC, service desk, infraestructura...)."""
    __tablename__ = "supplier_services"

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    subcontractor_id = Column(String(36), ForeignKey("subcontractors.id", ondelete="CASCADE"), nullable=False, index=True)
    contract_id = Column(String(36), ForeignKey("supplier_contracts.id", ondelete="SET NULL"), nullable=True, index=True)
    service_type = Column(String(50), nullable=False)   # clave de `custom_supplier_service_types`
    name = Column(String(255), nullable=False)
    scope = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="active")  # active|paused|ended
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    agent_group_id = Column(String(36), ForeignKey("sd_agent_groups.id", ondelete="SET NULL"), nullable=True, index=True)
    service_item_id = Column(String(36), ForeignKey("sd_service_items.id", ondelete="SET NULL"), nullable=True, index=True)
    alm_contract_id = Column(String(36), ForeignKey("alm_contracts.id", ondelete="SET NULL"), nullable=True, index=True)
    sla_response_hours = Column(Float, nullable=True)
    sla_resolution_hours = Column(Float, nullable=True)
    sla_target_pct = Column(Float, nullable=True)
    kpis = Column(JSON, nullable=True)               # [{"key","label","target","unit","direction":"higher|lower"}]
    contracted_units = Column(Float, nullable=True)
    unit = Column(String(50), nullable=True)
    reporting_frequency = Column(String(20), nullable=True)  # weekly|monthly|quarterly
    credit_rules = Column(JSON, nullable=True)       # [{"below_pct": 95, "credit_pct": 5}]
    bonus_rules = Column(JSON, nullable=True)        # [{"above_pct": 99, "bonus_pct": 2}]
    internal_owner_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    notes = Column(Text, nullable=True)
    # Migracion 191: fuente de medicion de dispositivos/usuarios (`proveedores.medicion`).
    metering_source = Column(String(20), nullable=True)          # manual|cmdb|external
    metering_config = Column(JSON, nullable=True)                # filtros de la CMDB / sistema externo, agregacion
    metering_last_at = Column(DateTime(timezone=True), nullable=True)
    metering_last_quantity = Column(Float, nullable=True)
    metering_last_error = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    subcontractor = relationship("Subcontractor")


class SupplierWorkPackage(Base):
    """Trabajo externalizado a una empresa: proyecto, fase, hito, entregable o tareas."""
    __tablename__ = "supplier_work_packages"

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    subcontractor_id = Column(String(36), ForeignKey("subcontractors.id", ondelete="CASCADE"), nullable=False, index=True)
    contract_id = Column(String(36), ForeignKey("supplier_contracts.id", ondelete="SET NULL"), nullable=True, index=True)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    scope_type = Column(String(20), nullable=False, default="tasks")  # project|phase|milestone|deliverable|tasks
    phase_id = Column(String(36), ForeignKey("project_phases.id", ondelete="SET NULL"), nullable=True, index=True)
    milestone_id = Column(String(36), ForeignKey("project_milestones.id", ondelete="SET NULL"), nullable=True, index=True)
    deliverable_id = Column(String(36), ForeignKey("deliverables.id", ondelete="SET NULL"), nullable=True, index=True)
    uat_session_id = Column(String(36), ForeignKey("uat_sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    acceptance_criteria = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="planned")  # planned|in_progress|delivered|accepted|rejected|cancelled
    planned_start = Column(Date, nullable=True)
    planned_end = Column(Date, nullable=True)
    delivered_at = Column(Date, nullable=True)
    accepted_at = Column(Date, nullable=True)
    accepted_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    rejection_reason = Column(Text, nullable=True)
    rejections = Column(Integer, default=0, nullable=False, server_default="0")
    price = Column(Money, nullable=True)
    currency = Column(String(3), nullable=True)
    progress_pct = Column(Float, nullable=True)
    last_report_at = Column(Date, nullable=True)
    internal_owner_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    legacy_assignment_id = Column(String(36), nullable=True)   # migracion 189: asignacion sin persona convertida
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    subcontractor = relationship("Subcontractor")
    project = relationship("Project")


class SupplierReport(Base):
    """Informe de avance (paquete) o periodico (servicio) del proveedor."""
    __tablename__ = "supplier_reports"

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    subcontractor_id = Column(String(36), ForeignKey("subcontractors.id", ondelete="CASCADE"), nullable=False, index=True)
    work_package_id = Column(String(36), ForeignKey("supplier_work_packages.id", ondelete="CASCADE"), nullable=True, index=True)
    service_id = Column(String(36), ForeignKey("supplier_services.id", ondelete="CASCADE"), nullable=True, index=True)
    period_start = Column(Date, nullable=True)
    period_end = Column(Date, nullable=True)
    progress_pct = Column(Float, nullable=True)
    summary = Column(Text, nullable=False)
    kpi_values = Column(JSON, nullable=True)         # {"<kpi>": valor}
    risks = Column(Text, nullable=True)
    # Migracion 191: tipo (progress|periodic|service_log|sla_evidence), evidencias y origen (internal|portal).
    report_type = Column(String(20), nullable=False, default="progress", server_default="progress")
    attachments = Column(JSON, nullable=True)        # [{"name","url","kind"}]
    submitted_via = Column(String(10), nullable=False, default="internal", server_default="internal")
    status = Column(String(20), nullable=False, default="submitted")  # submitted|reviewed
    submitted_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    reviewed_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    review_notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SupplierUsageRecord(Base):
    """Consumo registrado a mano o importado (dispositivos, llamadas, gastos...)."""
    __tablename__ = "supplier_usage_records"

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    subcontractor_id = Column(String(36), ForeignKey("subcontractors.id", ondelete="CASCADE"), nullable=False, index=True)
    contract_id = Column(String(36), ForeignKey("supplier_contracts.id", ondelete="CASCADE"), nullable=True, index=True)
    pricing_line_id = Column(String(36), ForeignKey("supplier_pricing_lines.id", ondelete="SET NULL"), nullable=True, index=True)
    service_id = Column(String(36), ForeignKey("supplier_services.id", ondelete="SET NULL"), nullable=True, index=True)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    unit = Column(String(50), nullable=True)
    quantity = Column(Float, nullable=False, default=0)
    amount = Column(Money, nullable=True)            # gastos: importe directo
    source = Column(String(20), nullable=False, default="manual")  # manual|import|cmdb|api
    description = Column(String(500), nullable=True)
    # Migracion 191: detalle del recuento (muestras, maximo, media, ultimo) y sistema de origen.
    detail = Column(JSON, nullable=True)
    source_system = Column(String(100), nullable=True)
    statement_id = Column(String(36), ForeignKey("supplier_statements.id", ondelete="SET NULL"), nullable=True, index=True)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SupplierStatement(Base):
    """Estado de cuenta de un periodo: la prevision cerrada de factura."""
    __tablename__ = "supplier_statements"

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    subcontractor_id = Column(String(36), ForeignKey("subcontractors.id", ondelete="CASCADE"), nullable=False, index=True)
    contract_id = Column(String(36), ForeignKey("supplier_contracts.id", ondelete="CASCADE"), nullable=False, index=True)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    currency = Column(String(3), nullable=True)
    lines = Column(JSON, nullable=True)              # detalle calculado
    subtotal = Column(Money, nullable=False, default=0)
    credits = Column(Float, nullable=False, default=0)
    bonus = Column(Float, nullable=False, default=0)
    adjustments = Column(Float, nullable=False, default=0)   # minimo comprometido / tope
    expected_amount = Column(Money, nullable=False, default=0)
    status = Column(String(20), nullable=False, default="closed")  # closed|reconciled|pending_approval|disputed|approved
    # Migracion 191: solicitud del motor de aprobaciones (tipo `supplier_statement`).
    approval_request_id = Column(String(36), nullable=True, index=True)
    invoice_id = Column(String(36), ForeignKey("subcontractor_invoices.id", ondelete="SET NULL"), nullable=True, index=True)
    invoice_amount = Column(Money, nullable=True)    # en moneda del contrato
    difference = Column(Float, nullable=True)
    difference_pct = Column(Float, nullable=True)
    dispute_reason = Column(Text, nullable=True)
    closed_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    approved_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    contract = relationship("SupplierContract")


class SupplierDocument(Base):
    """Documento o certificacion de un proveedor (DPA, NDA, ISO 27001, seguros...)."""
    __tablename__ = "supplier_documents"

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    subcontractor_id = Column(String(36), ForeignKey("subcontractors.id", ondelete="CASCADE"), nullable=False, index=True)
    doc_type = Column(String(40), nullable=False)
    reference = Column(String(255), nullable=True)
    issuer = Column(String(255), nullable=True)
    issued_at = Column(Date, nullable=True)
    expires_at = Column(Date, nullable=True)
    coverage_amount = Column(Money, nullable=True)
    document_url = Column(String(1000), nullable=True)
    notes = Column(Text, nullable=True)
    verified_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    expiry_notified_at = Column(Date, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False, server_default="1")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SupplierRiskAssessment(Base):
    """Evaluacion de riesgo y due diligence de un proveedor."""
    __tablename__ = "supplier_risk_assessments"

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    subcontractor_id = Column(String(36), ForeignKey("subcontractors.id", ondelete="CASCADE"), nullable=False, index=True)
    assessed_at = Column(Date, nullable=False)
    assessed_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    criteria = Column(JSON, nullable=False)          # {"data_access": 1-5, ...}
    score = Column(Float, nullable=False)
    level = Column(String(20), nullable=False)       # low|medium|high|critical
    next_review_date = Column(Date, nullable=True)
    due_diligence_done = Column(Boolean, default=False, nullable=False, server_default="0")
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SupplierAccessGrant(Base):
    """Registro de accesos del proveedor (o de una persona suya) a sistemas y datos."""
    __tablename__ = "supplier_access_grants"

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    subcontractor_id = Column(String(36), ForeignKey("subcontractors.id", ondelete="CASCADE"), nullable=False, index=True)
    worker_id = Column(String(36), ForeignKey("subcontractor_workers.id", ondelete="SET NULL"), nullable=True, index=True)
    system = Column(String(255), nullable=False)
    data_category = Column(String(100), nullable=True)
    access_level = Column(String(20), nullable=False, default="read")  # read|write|admin
    personal_data = Column(Boolean, default=False, nullable=False, server_default="0")
    justification = Column(Text, nullable=True)
    granted_at = Column(Date, nullable=False)
    granted_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    expires_at = Column(Date, nullable=True)
    revoked_at = Column(Date, nullable=True)
    revoked_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    revoke_reason = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
