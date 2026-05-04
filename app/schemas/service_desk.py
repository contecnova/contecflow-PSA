"""
Service Desk – Pydantic input schemas.

All request-body models are defined here so they can be tested independently
of the FastAPI router and reused across endpoints.
"""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, field_validator

from app.core.config import settings


# ── Ticket ────────────────────────────────────────────────────────────────────

class TicketCreateIn(BaseModel):
    title: str
    description: str
    ticket_type: str = "incident"
    urgency: str = "medium"
    impact: str = "user"
    priority: Optional[str] = None  # Auto-calculated if not provided
    service_item_id: Optional[str] = None
    project_id: Optional[str] = None
    contract_id: Optional[str] = None
    client_id: Optional[str] = None
    ci_id: Optional[str] = None
    tags: Optional[str] = None
    assigned_to_user_id: Optional[str] = None
    assigned_group_id: Optional[str] = None
    requester_name: Optional[str] = None
    requester_email: Optional[str] = None
    source: str = "portal"

    @field_validator('service_item_id', 'project_id', 'contract_id', 'client_id', 'ci_id',
                     'assigned_to_user_id', 'assigned_group_id', mode='before')
    @classmethod
    def empty_str_to_none(cls, v):
        return None if v == '' else v


class TicketUpdateIn(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    urgency: Optional[str] = None
    impact: Optional[str] = None
    support_level: Optional[str] = None
    assigned_to_user_id: Optional[str] = None
    assigned_group_id: Optional[str] = None
    ci_id: Optional[str] = None
    project_id: Optional[str] = None
    tags: Optional[str] = None
    resolution: Optional[str] = None
    resolution_code: Optional[str] = None
    problem_id: Optional[str] = None

    @field_validator('assigned_to_user_id', 'assigned_group_id', 'ci_id',
                     'project_id', 'problem_id', mode='before')
    @classmethod
    def empty_str_to_none(cls, v):
        return None if v == '' else v


class CommentIn(BaseModel):
    body: str
    is_public: bool = True


class TimeLogIn(BaseModel):
    minutes: int
    description: Optional[str] = None
    billable: bool = False


class CSATIn(BaseModel):
    score: int
    comment: Optional[str] = None


class MergeIn(BaseModel):
    merged_ticket_id: str
    reason: Optional[str] = None


class SplitTicketIn(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    ticket_type: Optional[str] = None
    priority: Optional[str] = None
    urgency: Optional[str] = None
    impact: Optional[str] = None
    support_level: Optional[str] = None
    tags: Optional[str] = None
    copy_latest_comments: int = 0


# ── Problem ───────────────────────────────────────────────────────────────────

class ProblemIn(BaseModel):
    title: str
    description: str
    priority: str = "p2_high"
    ci_id: Optional[str] = None
    project_id: Optional[str] = None
    owner_user_id: Optional[str] = None


class ProblemUpdateIn(BaseModel):
    status: Optional[str] = None
    root_cause: Optional[str] = None
    workaround: Optional[str] = None
    fix_description: Optional[str] = None
    owner_user_id: Optional[str] = None


# ── Knowledge Base ────────────────────────────────────────────────────────────

class KBArticleIn(BaseModel):
    title: str
    body: str
    summary: Optional[str] = None
    category_id: Optional[str] = None
    tags: Optional[str] = None
    is_public: bool = True
    status: str = "draft"
    created_from_ticket_id: Optional[str] = None


class KBArticleUpdate(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    summary: Optional[str] = None
    tags: Optional[str] = None
    is_public: Optional[bool] = None
    status: Optional[str] = None


# ── Service Catalog ───────────────────────────────────────────────────────────

class ServiceCategoryIn(BaseModel):
    name: str
    description: Optional[str] = None
    icon: str = "🔧"
    color: str = "#00d4ff"
    sort_order: int = 0


class ServiceItemIn(BaseModel):
    category_id: str
    name: str
    description: Optional[str] = None
    ticket_type: str = "service_request"
    default_priority: str = "p3_medium"
    default_support_level: str = "l1"
    sla_response_hours: float = 8
    sla_resolution_hours: float = 24
    requires_approval: bool = False
    is_visible_to_clients: bool = True
    sort_order: int = 0


class ServiceItemUpdate(BaseModel):
    category_id: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    ticket_type: Optional[str] = None
    default_priority: Optional[str] = None
    default_support_level: Optional[str] = None
    sla_response_hours: Optional[float] = None
    sla_resolution_hours: Optional[float] = None
    requires_approval: Optional[bool] = None
    is_visible_to_clients: Optional[bool] = None
    sort_order: Optional[int] = None


# ── SLA ───────────────────────────────────────────────────────────────────────

class SLAPolicyIn(BaseModel):
    name: str
    is_default: bool = False
    p1_response_hours: float = 1
    p1_resolution_hours: float = 4
    p2_response_hours: float = 4
    p2_resolution_hours: float = 8
    p3_response_hours: float = 8
    p3_resolution_hours: float = 24
    p4_response_hours: float = 24
    p4_resolution_hours: float = 72
    business_hours_only: bool = True


class HolidayIn(BaseModel):
    name: str
    holiday_date: str   # YYYY-MM-DD
    country: Optional[str] = None
    sla_policy_id: Optional[str] = None


# ── Configuration Items ───────────────────────────────────────────────────────

class CIIn(BaseModel):
    name: str
    ci_type: str
    status: str = "operational"
    description: Optional[str] = None
    project_id: Optional[str] = None
    owner_user_id: Optional[str] = None
    environment: Optional[str] = None
    version: Optional[str] = None
    location: Optional[str] = None
    vendor: Optional[str] = None
    criticality: str = "medium"
    sla_policy_id: Optional[str] = None


# ── Agent Groups ──────────────────────────────────────────────────────────────

class AgentGroupIn(BaseModel):
    name: str
    description: Optional[str] = None
    support_level: str = "l1"


# ── Announcements ─────────────────────────────────────────────────────────────

class AnnouncementIn(BaseModel):
    title: str
    body: str
    type: str = "info"
    show_to_clients: bool = True
    ci_id: Optional[str] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None


# ── Escalation Rules ──────────────────────────────────────────────────────────

class EscalationRuleIn(BaseModel):
    name: str
    trigger: str
    action: str
    applies_to_priority: Optional[str] = None   # JSON list or blank for all
    idle_hours_threshold: Optional[float] = None
    group_id: Optional[str] = None
    target_group_id: Optional[str] = None
    notify_user_ids: Optional[str] = None        # JSON list
    target_priority: Optional[str] = None
    sort_order: int = 100
    is_active: bool = True


# ── Assets ────────────────────────────────────────────────────────────────────

class AssetIn(BaseModel):
    name: str
    asset_type: str
    serial_number: Optional[str] = None
    model: Optional[str] = None
    manufacturer: Optional[str] = None
    part_number: Optional[str] = None
    license_key: Optional[str] = None
    license_seats: Optional[int] = None
    purchase_date: Optional[str] = None
    warranty_expiry: Optional[str] = None
    eol_date: Optional[str] = None
    lease_expiry: Optional[str] = None
    purchase_price: Optional[float] = None
    current_value: Optional[float] = None
    currency: str = settings.DEFAULT_CURRENCY
    po_number: Optional[str] = None
    vendor: Optional[str] = None
    vendor_contract: Optional[str] = None
    location: Optional[str] = None
    assigned_user_id: Optional[str] = None
    department: Optional[str] = None
    ci_id: Optional[str] = None
    tags: Optional[str] = None
    notes: Optional[str] = None
    managed_by_user_id: Optional[str] = None


class AssetUpdate(AssetIn):
    name: Optional[str] = None
    asset_type: Optional[str] = None
    status: Optional[str] = None


# ── Status Page ───────────────────────────────────────────────────────────────

class StatusComponentIn(BaseModel):
    name: str
    description: Optional[str] = None
    group_name: Optional[str] = None
    sort_order: int = 0
    status: str = "operational"
    is_public: bool = True
    ci_id: Optional[str] = None


class StatusIncidentIn(BaseModel):
    title: str
    status: str = "investigating"
    impact: str = "partial_outage"
    update_message: Optional[str] = None
    ticket_id: Optional[str] = None


class StatusIncidentUpdateIn(BaseModel):
    status: str
    message: str


# ── Canned Responses ──────────────────────────────────────────────────────────

class CannedResponseIn(BaseModel):
    title:    str
    body:     str
    category: Optional[str] = None
    shortcut: Optional[str] = None
    is_active: bool = True


# ── On-Call Schedules ────────────────────────────────────────────────────────

class OnCallScheduleIn(BaseModel):
    name: str
    group_id: str
    rotation: str = "weekly"
    timezone: str = settings.DEFAULT_TIMEZONE
    description: Optional[str] = None


class OnCallEntryIn(BaseModel):
    user_id: str
    start_dt: datetime
    end_dt: datetime
    notes: Optional[str] = None
