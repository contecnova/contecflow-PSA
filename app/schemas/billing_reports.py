from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings


# ── Invoice output schemas (replaces _invoice_out dict) ───────────────────────

class InvoiceLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Identificador único de la línea de factura")
    order: int = Field(..., description="Orden de la línea en la factura")
    description: str = Field(..., description="Descripción del concepto facturado")
    quantity: float = Field(..., description="Cantidad facturada")
    unit: Optional[str] = Field(default=None, description="Unidad de medida (horas, días, etc.)")
    unit_price: float = Field(..., description="Precio unitario en euros")
    discount_pct: float = Field(..., description="Porcentaje de descuento aplicado")
    amount: float = Field(..., description="Importe total de la línea en euros")
    source_type: Optional[str] = Field(default=None, description="Tipo de origen del concepto (imputación, milestone...)")


class InvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Identificador único de la factura")
    number: str = Field(..., description="Número de factura")
    project_id: Optional[str] = Field(default=None, description="ID del proyecto facturado")
    client_id: Optional[str] = Field(default=None, description="ID del cliente facturado")
    project_name: Optional[str] = Field(default=None, description="Nombre del proyecto facturado")
    project_code: Optional[str] = Field(default=None, description="Código del proyecto facturado")
    client_name: Optional[str] = Field(default=None, description="Nombre del cliente facturado")
    client_email: Optional[str] = Field(default=None, description="Email de contacto del cliente")
    client_vat: Optional[str] = Field(default=None, description="NIF/CIF del cliente")
    subtotal: Optional[float] = Field(default=None, description="Subtotal de la factura en euros")
    tax_rate: Optional[float] = Field(default=None, description="Tipo impositivo aplicado")
    tax_amount: Optional[float] = Field(default=None, description="Importe de impuestos en euros")
    total: Optional[float] = Field(default=None, description="Importe total de la factura en euros")
    currency: Optional[str] = Field(default=None, description="Moneda de la factura")
    issue_date: Optional[date] = Field(default=None, description="Fecha de emisión de la factura")
    due_date: Optional[date] = Field(default=None, description="Fecha de vencimiento de la factura")
    paid_date: Optional[date] = Field(default=None, description="Fecha de pago de la factura")
    status: Optional[str] = Field(default=None, description="Estado de la factura")
    notes: Optional[str] = Field(default=None, description="Notas internas de la factura")
    po_reference: Optional[str] = Field(default=None, description="Referencia de la orden de compra del cliente")
    period_from: Optional[date] = Field(default=None, description="Inicio del periodo facturado")
    period_to: Optional[date] = Field(default=None, description="Fin del periodo facturado")
    lines: List[InvoiceLineOut] = Field(default=[], description="Lista de líneas de la factura")
    created_at: Optional[datetime] = Field(default=None, description="Fecha de creación de la factura")


# ── Generic ────────────────────────────────────────────────────────────────────

class OkResponse(BaseModel):
    ok: bool = Field(default=True, description="Indica que la operación se completó correctamente")


class InvoiceStatusOut(BaseModel):
    count: int = Field(..., description="Número de facturas en este estado")
    total: float = Field(..., description="Importe total agregado en euros")


class InvoiceSummaryOut(BaseModel):
    by_status: Dict[str, InvoiceStatusOut] = Field(..., description="Agregación de facturas por estado")
    total_invoiced: float = Field(..., description="Importe total facturado en euros")
    total_paid: float = Field(..., description="Importe total cobrado en euros")
    total_pending: float = Field(..., description="Importe pendiente de cobro en euros")
    overdue_count: int = Field(..., description="Número de facturas vencidas")
    overdue_amount: float = Field(..., description="Importe vencido total en euros")


class InvoiceStatusUpdateOut(BaseModel):
    ok: bool = Field(..., description="Indica si la actualización se realizó correctamente")
    status: str = Field(..., description="Nuevo estado aplicado a la factura")


# ── Approval workflow output schemas ───────────────────────────────────────────

class WorkflowStepOut(BaseModel):
    id: str
    step_order: int
    name: str
    approver_type: str
    approver_role: Optional[str] = None
    approver_user_id: Optional[str] = None
    approver_user_name: Optional[str] = None
    is_optional: bool = False
    timeout_hours: int = 72
    on_timeout: str = "escalate"
    model_config = {"from_attributes": True}


class WorkflowOut(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    entity_type: str
    is_active: bool = True
    is_default: bool = False
    trigger_conditions: Optional[str] = None
    step_count: int = 0
    created_at: Optional[str] = None
    steps: Optional[List[WorkflowStepOut]] = None
    model_config = {"from_attributes": True}


class ApprovalDecisionItemOut(BaseModel):
    step_order: int
    approver_id: str
    approver_name: Optional[str] = None
    decision: str
    note: Optional[str] = None
    decided_at: Optional[str] = None


class ApprovalRequestOut(BaseModel):
    id: str
    workflow_id: Optional[str] = None
    entity_type: str
    entity_id: str
    entity_summary: Optional[str] = None
    requested_by: str
    requester_name: Optional[str] = None
    current_step: int = 1
    status: str
    final_decision: Optional[str] = None
    final_note: Optional[str] = None
    completed_at: Optional[str] = None
    created_at: Optional[str] = None
    decisions: List[ApprovalDecisionItemOut] = []
    # Optional fields added by pending-my-action endpoint
    step_name: Optional[str] = None
    step_order: Optional[int] = None
    model_config = {"from_attributes": True}


class ApprovalStatsOut(BaseModel):
    total: int
    pending: int
    approved: int
    rejected: int
    by_entity_type: Dict[str, int] = {}


# ── Report / Import / ITSM output schemas ─────────────────────────────────────

class ReportSaveOut(BaseModel):
    ok: bool
    id: str


class ImportTemplateOut(BaseModel):
    entity_type: str
    columns: List[str]
    example: List[List[str]] = []
    instructions: str


class ImportValidationErrorOut(BaseModel):
    row: int
    field: str
    error: str


class ImportValidateOut(BaseModel):
    valid: bool
    total_rows: int
    errors: List[ImportValidationErrorOut] = []
    warnings: List[str] = []
    preview: List[Dict[str, Any]] = []


class ImportExecuteOut(BaseModel):
    job_id: str
    status: str
    total: int
    succeeded: int
    failed: int
    errors: List[Dict[str, Any]] = []


class SlaTicketMiniOut(BaseModel):
    id: str
    number: Optional[str] = None
    title: str
    priority: Optional[str] = None
    status: Optional[str] = None
    assigned_to: Optional[str] = None
    sla_due: Optional[str] = None
    breach_minutes: Optional[int] = None
    remaining_minutes: Optional[int] = None
    requester: Optional[str] = None


class SlaPriorityComplianceOut(BaseModel):
    total: int
    breached: int
    compliance_pct: float


class SlaRealTimeOut(BaseModel):
    open: int
    breached: int
    at_risk_2h: int
    at_risk_4h: int
    healthy: int


class SlaHeatmapPointOut(BaseModel):
    day: int
    hour: int
    count: int


class SlaDashboardOut(BaseModel):
    real_time: SlaRealTimeOut
    breached_tickets: List[SlaTicketMiniOut] = []
    at_risk_tickets: List[SlaTicketMiniOut] = []
    compliance_by_priority: Dict[str, SlaPriorityComplianceOut] = {}
    volume_heatmap: List[SlaHeatmapPointOut] = []


class AgentPerformanceOut(BaseModel):
    user_id: str
    user_name: str
    total: int
    resolved: int
    breached: int
    total_mttr: float
    csat_sum: float
    csat_count: int
    open: int
    avg_mttr_hours: float
    avg_csat: Optional[float] = None
    sla_compliance_pct: float
    resolution_rate_pct: float


class SlaPauseResumeOut(BaseModel):
    ok: bool
    message: str
    sla_resolution_due: Optional[str] = None


class ImportJobHistoryOut(BaseModel):
    id: str
    entity_type: str
    filename: Optional[str] = None
    status: str
    total_rows: int
    succeeded: int
    failed_rows: int
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class WorkflowStepConfigOut(BaseModel):
    id: str
    order: int
    step_type: str
    name: Optional[str] = None
    config: Dict[str, Any] = {}
    next_step_yes: Optional[str] = None
    next_step_no: Optional[str] = None


class AutomationWorkflowOut(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    is_global: bool = False
    status: str
    trigger_type: str
    trigger_conditions: Optional[Dict[str, Any]] = None
    steps: List[WorkflowStepConfigOut] = []
    run_count: int = 0
    success_count: int = 0
    error_count: int = 0
    last_run_at: Optional[str] = None


class WorkflowExecutionOut(BaseModel):
    id: str
    status: str
    current_step: int
    steps_log: List[Dict[str, Any]] = []
    error: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class ScheduledReportOut(BaseModel):
    id: str
    name: str
    metric: Optional[str] = None
    frequency: str
    recipients: List[str] = []
    include_pdf: bool = True
    is_active: bool = True
    last_run_at: Optional[str] = None
    next_run_at: Optional[str] = None
    created_at: Optional[str] = None


class ScheduledReportCreateOut(BaseModel):
    ok: bool
    id: str


class ScheduledReportRunOut(BaseModel):
    ok: bool
    recipients: List[str] = []


class TemplateTaskOut(BaseModel):
    id: str
    title: str
    estimated_hours: Optional[float] = None
    skill_required: Optional[str] = None


class TemplatePhaseOut(BaseModel):
    id: str
    name: str
    order: int
    estimated_weeks: Optional[int] = None
    tasks: List[TemplateTaskOut] = []


class ProjectTemplateOut(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    project_type: Optional[str] = None
    estimated_weeks: Optional[int] = None
    estimated_hours: Optional[float] = None
    phases: List[TemplatePhaseOut] = []
    risk_count: int = 0
    deliverable_count: int = 0


class TemplateCreateOut(BaseModel):
    ok: bool
    id: str


class TemplateInstantiateOut(BaseModel):
    ok: bool
    project_id: str
    project_code: str
    project_name: str
    phases_created: int
    tasks_created: int


class SmartMatchQueryOut(BaseModel):
    skills: List[str] = []
    role: Optional[str] = None
    hours_needed: float
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class SmartMatchScoresOut(BaseModel):
    overall: float
    skills: float
    availability: float
    workload: float
    cost: float


class SmartMatchCandidateOut(BaseModel):
    user_id: str
    user_name: str
    role: Optional[str] = None
    department: Optional[str] = None
    job_title: Optional[str] = None
    hourly_rate: float
    weekly_capacity: float
    active_tasks: int
    matched_skills: List[str] = []
    missing_skills: List[str] = []
    avg_skill_level: float
    availability_hours: float
    scores: SmartMatchScoresOut
    recommendation: str


class SmartMatchOut(BaseModel):
    query: SmartMatchQueryOut
    candidates: List[SmartMatchCandidateOut] = []
    total_evaluated: int
    message: str


# ── Report ─────────────────────────────────────────────────────────────────────

class ReportSave(BaseModel):
    name: str = Field(..., description="Nombre del informe")
    description: Optional[str] = Field(default=None, description="Descripción del informe")
    category: Optional[str] = Field(default="custom", description="Categoría del informe")
    icon: str = Field(default="📊", description="Icono representativo del informe")
    is_public: bool = Field(default=False, description="Indica si el informe es público para toda la organización")
    data_source: str = Field(..., description="Origen de datos del informe")
    filters: Optional[dict] = Field(default=None, description="Filtros aplicados al informe")
    columns: Optional[list] = Field(default=None, description="Columnas a mostrar en el informe")
    group_by: Optional[str] = Field(default=None, description="Campo por el que se agrupan los resultados")
    chart_type: Optional[str] = Field(default="table", description="Tipo de visualización (table, bar, line...)")
    chart_x: Optional[str] = Field(default=None, description="Campo usado como eje X del gráfico")
    chart_y: Optional[str] = Field(default=None, description="Campo usado como eje Y del gráfico")
    schedule_cron: Optional[str] = Field(default=None, description="Expresión cron para envío programado del informe")
    schedule_emails: Optional[list] = Field(default=None, description="Lista de emails destinatarios del envío programado")


class InvoiceCreate(BaseModel):
    project_id: Optional[str] = Field(default=None, description="ID del proyecto a facturar")
    contract_id: Optional[str] = Field(default=None, description="ID del contrato asociado a la factura")
    client_name: Optional[str] = Field(default=None, description="Nombre del cliente facturado")
    client_address: Optional[str] = Field(default=None, description="Dirección postal del cliente")
    client_vat: Optional[str] = Field(default=None, description="NIF/CIF del cliente")
    client_email: Optional[str] = Field(default=None, description="Email de contacto del cliente")
    issue_date: date = Field(..., description="Fecha de emisión de la factura")
    due_date: Optional[date] = Field(default=None, description="Fecha de vencimiento de la factura")
    tax_rate: float = Field(default=settings.DEFAULT_TAX_RATE, description="Tipo impositivo aplicado")
    currency: str = Field(default=settings.DEFAULT_CURRENCY, description="Moneda de la factura")
    notes: Optional[str] = Field(default=None, description="Notas internas de la factura")
    po_reference: Optional[str] = Field(default=None, description="Referencia de la orden de compra del cliente")
    period_from: Optional[date] = Field(default=None, description="Inicio del periodo facturado")
    period_to: Optional[date] = Field(default=None, description="Fin del periodo facturado")
    lines: List[dict] = Field(default=[], description="Líneas de la factura")


class WorkflowCreate(BaseModel):
    name: str
    description: Optional[str] = None
    project_id: Optional[str] = None
    is_global: bool = False
    trigger_type: str
    trigger_conditions: Optional[dict] = None
    steps: List[dict] = []


class TemplateCreate(BaseModel):
    name: str
    description: Optional[str] = None
    project_type: Optional[str] = None
    estimated_weeks: Optional[int] = None
    estimated_hours: Optional[float] = None
    phases: List[dict] = []
    risks: List[dict] = []
    deliverables: List[dict] = []


class ScheduledReportCreate(BaseModel):
    name: str
    metric: Optional[str] = "hours_by_month"
    frequency: str = "weekly"
    recipients: List[str] = []
    include_pdf: bool = True
    filters_json: Optional[str] = "{}"
    # Revisión 2026-11: el alta los ignoraba; sólo los aceptaba la edición.
    report_type: Optional[str] = "custom"
    include_narrative: bool = False
    day_of_week: Optional[int] = Field(None, ge=0, le=6)
    day_of_month: Optional[int] = Field(None, ge=1, le=31)
    send_hour: Optional[int] = Field(None, ge=0, le=23)
    recipients_extra: List[str] = []
