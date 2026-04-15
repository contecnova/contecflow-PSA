from datetime import date
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


# ── Generic ────────────────────────────────────────────────────────────────────

class OkResponse(BaseModel):
    ok: bool = True


# ── Invoice output schemas ─────────────────────────────────────────────────────

class InvoiceLineOut(BaseModel):
    id: str
    order: int
    description: str
    quantity: float
    unit: Optional[str] = None
    unit_price: float
    discount_pct: float = 0.0
    amount: float
    source_type: Optional[str] = None
    model_config = {"from_attributes": True}


class InvoiceOut(BaseModel):
    id: str
    number: str
    project_id: Optional[str] = None
    client_id: Optional[str] = None
    project_name: Optional[str] = None
    project_code: Optional[str] = None
    client_name: Optional[str] = None
    client_email: Optional[str] = None
    client_vat: Optional[str] = None
    subtotal: float = 0.0
    tax_rate: float = 0.0
    tax_amount: float = 0.0
    total: float = 0.0
    currency: str = "EUR"
    issue_date: Optional[date] = None
    due_date: Optional[date] = None
    paid_date: Optional[date] = None
    status: str = "draft"
    notes: Optional[str] = None
    po_reference: Optional[str] = None
    period_from: Optional[date] = None
    period_to: Optional[date] = None
    lines: List[InvoiceLineOut] = []
    created_at: Optional[str] = None
    model_config = {"from_attributes": True}


class InvoiceStatusOut(BaseModel):
    count: int
    total: float


class InvoiceSummaryOut(BaseModel):
    by_status: Dict[str, InvoiceStatusOut]
    total_invoiced: float
    total_paid: float
    total_pending: float
    overdue_count: int
    overdue_amount: float


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


# ── Report ─────────────────────────────────────────────────────────────────────

class ReportSave(BaseModel):
    name: str
    description: Optional[str] = None
    category: Optional[str] = "custom"
    icon: str = "📊"
    is_public: bool = False
    data_source: str
    filters: Optional[dict] = None
    columns: Optional[list] = None
    group_by: Optional[str] = None
    chart_type: Optional[str] = "table"
    chart_x: Optional[str] = None
    chart_y: Optional[str] = None
    schedule_cron: Optional[str] = None
    schedule_emails: Optional[list] = None


class InvoiceCreate(BaseModel):
    project_id: Optional[str] = None
    contract_id: Optional[str] = None
    client_name: Optional[str] = None
    client_address: Optional[str] = None
    client_vat: Optional[str] = None
    client_email: Optional[str] = None
    issue_date: date
    due_date: Optional[date] = None
    tax_rate: float = 21.0
    currency: str = "EUR"
    notes: Optional[str] = None
    po_reference: Optional[str] = None
    period_from: Optional[date] = None
    period_to: Optional[date] = None
    lines: List[dict] = []


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
