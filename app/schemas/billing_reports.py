from datetime import date
from typing import List, Optional

from pydantic import BaseModel


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
