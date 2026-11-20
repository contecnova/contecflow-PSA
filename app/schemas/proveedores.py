"""Esquemas de `/suppliers` (proveedores y externalizacion, migracion 189)."""
from __future__ import annotations

from datetime import date
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field

Tipo = Literal["freelance", "company"]
Modo = Literal["staff_augmentation", "outsourcing", "managed_services"]
ModeloDeCobro = Literal["per_resource", "fixed_price", "per_unit", "subscription", "expense", "bonus"]
Periodo = Literal["monthly", "quarterly", "annual", "one_time"]
TipoDeContrato = Literal["msa", "sow", "service", "framework", "freelance"]
Alcance = Literal["project", "phase", "milestone", "deliverable", "tasks"]
# Migracion 191
TipoDeInforme = Literal["progress", "periodic", "service_log", "sla_evidence"]
FuenteDeMedicion = Literal["manual", "cmdb", "external"]
TipoDeDocumento = Literal[
    "dpa_art28", "nda", "iso27001", "soc2", "ens", "insurance_liability", "insurance_cyber",
    "security_questionnaire", "due_diligence", "tax_certificate", "social_security_certificate", "other",
]


class Clasificacion(BaseModel):
    kind: Optional[Tipo] = Field(None, description="freelance (persona física) o company")
    engagement_modes: Optional[List[Modo]] = Field(None, description="Modos de relación (combinables)")
    training_enabled: Optional[bool] = Field(None, description="Formación y evaluaciones internas para sus personas")
    alm_vendor_id: Optional[str] = Field(None, description="Mismo proveedor en ALM (licencias, soporte)")
    internal_owner_id: Optional[str] = Field(None, description="Responsable interno del proveedor")
    legal_name: Optional[str] = Field(None, description="Razón social")
    website: Optional[str] = Field(None, description="Web")
    address: Optional[str] = Field(None, description="Dirección")
    data_access: Optional[bool] = Field(None, description="Accede a datos personales (exige DPA art. 28)")
    data_categories: Optional[str] = Field(None, description="Categorías de datos a las que accede")
    systems_access: Optional[str] = Field(None, description="Sistemas a los que accede")


class AltaDeFreelance(BaseModel):
    name: str = Field(..., description="Nombre de la persona")
    email: Optional[str] = Field(None, description="Correo")
    phone: Optional[str] = Field(None, description="Teléfono")
    vat_number: Optional[str] = Field(None, description="NIF")
    country: Optional[str] = Field(None, description="País")
    currency: Optional[str] = Field(None, description="Moneda (por defecto, la de la empresa)")
    role: Optional[str] = Field(None, description="Perfil o puesto")
    cost_rate: Optional[float] = Field(None, ge=0, description="Coste por hora")
    sell_rate: Optional[float] = Field(None, ge=0, description="Venta por hora")
    weekly_capacity_hours: Optional[float] = Field(None, gt=0, description="Horas semanales")
    available_from: Optional[date] = Field(None, description="Disponible desde")
    available_until: Optional[date] = Field(None, description="Disponible hasta")
    internal_owner_id: str = Field(..., description="Responsable interno (obligatorio)")
    has_access: bool = Field(True, description="Con acceso (login)")
    access_until: Optional[date] = Field(None, description="Fin del acceso")
    engagement_modes: Optional[List[Modo]] = Field(None, description="Por defecto staff_augmentation")
    training_enabled: bool = Field(False, description="Formación y evaluaciones internas")
    notes: Optional[str] = Field(None, description="Notas")


class Motivo(BaseModel):
    reason: Optional[str] = Field(None, max_length=255, description="Motivo")


class ContratoIn(BaseModel):
    title: Optional[str] = Field(None, description="Título")
    code: Optional[str] = Field(None, max_length=30, description="Referencia")
    contract_type: Optional[TipoDeContrato] = Field(None, description="Tipo de contrato")
    modes: Optional[List[Modo]] = Field(None, description="Modos que cubre")
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    auto_renew: Optional[bool] = None
    notice_days: Optional[int] = Field(None, ge=0)
    currency: Optional[str] = Field(None, max_length=3)
    committed_minimum: Optional[float] = Field(None, ge=0)
    minimum_period: Optional[Periodo] = None
    total_cap: Optional[float] = Field(None, ge=0)
    po_number: Optional[str] = None
    po_amount: Optional[float] = Field(None, ge=0)
    budget_id: Optional[str] = None
    project_id: Optional[str] = None
    cost_center_id: Optional[str] = None
    payment_terms_days: Optional[int] = Field(None, ge=0)
    expenses_rebillable: Optional[bool] = None
    expenses_cap: Optional[float] = Field(None, ge=0)
    internal_owner_id: Optional[str] = None
    document_url: Optional[str] = None
    notes: Optional[str] = None


class Tramo(BaseModel):
    model_config = {"populate_by_name": True}
    desde: float = Field(0, ge=0, alias="from", description="Desde (unidades)")
    hasta: Optional[float] = Field(None, alias="to", description="Hasta (vacío: sin límite)")
    price: float = Field(..., ge=0, description="Precio por unidad en el tramo")


class LineaIn(BaseModel):
    model: Optional[ModeloDeCobro] = Field(None, description="Modelo de cobro")
    unit: Optional[str] = Field(None, description="Unidad (catálogo de unidades de cobro)")
    description: Optional[str] = None
    rate_id: Optional[str] = Field(None, description="Perfil (tarifa del proveedor) para por recurso")
    service_id: Optional[str] = None
    work_package_id: Optional[str] = None
    unit_price: Optional[float] = Field(None, ge=0)
    period: Optional[Periodo] = None
    included_units: Optional[float] = Field(None, ge=0)
    overage_price: Optional[float] = Field(None, ge=0)
    tiers: Optional[List[Tramo]] = None
    min_amount: Optional[float] = Field(None, ge=0)
    max_amount: Optional[float] = Field(None, ge=0)
    valid_from: Optional[date] = None
    valid_until: Optional[date] = None
    is_active: Optional[bool] = None


class ReglaDeCredito(BaseModel):
    below_pct: float = Field(..., ge=0, le=100)
    credit_pct: float = Field(..., ge=0, le=100)


class ReglaDeBonus(BaseModel):
    above_pct: float = Field(..., ge=0, le=100)
    bonus_pct: float = Field(..., ge=0, le=100)


class Kpi(BaseModel):
    key: str
    label: str
    target: Optional[float] = None
    unit: Optional[str] = None
    direction: Literal["higher", "lower"] = "higher"


class ServicioIn(BaseModel):
    service_type: Optional[str] = Field(None, description="Clave del catálogo de tipos de servicio")
    name: Optional[str] = None
    scope: Optional[str] = None
    contract_id: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    agent_group_id: Optional[str] = Field(None, description="Cola del service desk del proveedor")
    service_item_id: Optional[str] = None
    alm_contract_id: Optional[str] = None
    sla_response_hours: Optional[float] = Field(None, gt=0)
    sla_resolution_hours: Optional[float] = Field(None, gt=0)
    sla_target_pct: Optional[float] = Field(None, ge=0, le=100)
    kpis: Optional[List[Kpi]] = None
    contracted_units: Optional[float] = Field(None, ge=0)
    unit: Optional[str] = None
    reporting_frequency: Optional[Literal["weekly", "monthly", "quarterly"]] = None
    credit_rules: Optional[List[ReglaDeCredito]] = None
    bonus_rules: Optional[List[ReglaDeBonus]] = None
    internal_owner_id: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[Literal["active", "paused", "ended"]] = None
    # Migracion 191: fuente de medicion de dispositivos/usuarios (`proveedores.medicion`).
    metering_source: Optional[FuenteDeMedicion] = Field(None, description="manual, cmdb o external")
    metering_config: Optional[dict[str, Any]] = Field(
        None, description="cmdb: ci_types, ci_classes, environment, vendor, location, project_id, "
                          "software_product_id, seen_within_days, count (devices|owners), aggregation; "
                          "external: system, aggregation (last|max|average)")


class PaqueteIn(BaseModel):
    project_id: Optional[str] = None
    contract_id: Optional[str] = None
    scope_type: Optional[Alcance] = None
    phase_id: Optional[str] = None
    milestone_id: Optional[str] = None
    deliverable_id: Optional[str] = None
    uat_session_id: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    acceptance_criteria: Optional[str] = None
    planned_start: Optional[date] = None
    planned_end: Optional[date] = None
    price: Optional[float] = Field(None, ge=0)
    currency: Optional[str] = Field(None, max_length=3)
    progress_pct: Optional[float] = Field(None, ge=0, le=100)
    internal_owner_id: Optional[str] = None


class TareasDelPaquete(BaseModel):
    task_ids: List[str] = Field(..., min_length=1, max_length=500)


class AdjuntoEnlace(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    url: str = Field(..., min_length=8, max_length=1000, description="Enlace http(s) a la evidencia")


class InformeIn(BaseModel):
    work_package_id: Optional[str] = None
    service_id: Optional[str] = None
    report_type: Optional[TipoDeInforme] = Field(
        None, description="progress (paquete), periodic, service_log o sla_evidence (servicio)")
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    progress_pct: Optional[float] = Field(None, ge=0, le=100)
    summary: str = Field(..., min_length=1, max_length=20000)
    kpi_values: Optional[dict[str, Any]] = None
    risks: Optional[str] = Field(None, max_length=10000)
    attachments: Optional[List[AdjuntoEnlace]] = Field(None, max_length=20, description="Evidencias por enlace")


class ContactoDelPortalIn(BaseModel):
    supplier_portal: bool = Field(..., description="Contacto del portal del proveedor")


class RecuentoIn(BaseModel):
    """Recuento de un sistema externo (SIEM, consola del proveedor, MDM)."""
    quantity: Optional[float] = Field(None, ge=0, description="Dispositivos o usuarios contados")
    items: Optional[List[str]] = Field(None, max_length=200000,
                                       description="Identificadores a contar sin duplicados (no se guardan)")
    as_of: Optional[date] = Field(None, description="Fecha del recuento (hoy por defecto)")
    system: Optional[str] = Field(None, max_length=100, description="Sistema de origen")


class FilaDeRecuento(RecuentoIn):
    service_id: str


class ImportacionDeRecuentosIn(BaseModel):
    rows: List[FilaDeRecuento] = Field(..., min_length=1, max_length=5000)


class VistaPreviaDeMedicionIn(BaseModel):
    metering_source: FuenteDeMedicion
    metering_config: Optional[dict[str, Any]] = None
    unit: Optional[str] = None


class RevisionIn(BaseModel):
    review_notes: Optional[str] = None


class ConsumoIn(BaseModel):
    contract_id: Optional[str] = None
    pricing_line_id: Optional[str] = None
    service_id: Optional[str] = None
    project_id: Optional[str] = None
    period_start: date
    period_end: date
    unit: Optional[str] = None
    quantity: float = Field(0, ge=0)
    amount: Optional[float] = Field(None, ge=0)
    source: Literal["manual", "import"] = "manual"
    description: Optional[str] = Field(None, max_length=500)


class PeriodoIn(BaseModel):
    period_start: date
    period_end: date


class ConciliarIn(BaseModel):
    invoice_id: str


class DocumentoIn(BaseModel):
    doc_type: Optional[TipoDeDocumento] = None
    reference: Optional[str] = None
    issuer: Optional[str] = None
    issued_at: Optional[date] = None
    expires_at: Optional[date] = None
    coverage_amount: Optional[float] = Field(None, ge=0)
    document_url: Optional[str] = None
    notes: Optional[str] = None
    verified: Optional[bool] = Field(None, description="Marcar como verificado por quien lo guarda")


class EvaluacionIn(BaseModel):
    criteria: dict[str, int] = Field(..., description="Criterios 1-5: data_access, criticality, dependency, "
                                                       "financial, location, security")
    due_diligence_done: bool = False
    notes: Optional[str] = None
    assessed_at: Optional[date] = None


class AccesoIn(BaseModel):
    worker_id: Optional[str] = None
    system: str = Field(..., min_length=1, max_length=255)
    data_category: Optional[str] = Field(None, max_length=100)
    access_level: Literal["read", "write", "admin"] = "read"
    personal_data: bool = False
    justification: Optional[str] = None
    granted_at: Optional[date] = None
    expires_at: Optional[date] = None
