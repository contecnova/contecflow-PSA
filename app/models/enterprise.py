"""
Enterprise models:
  - AuditLog     : Immutable audit trail for every data change
  - ProjectPermission: Per-project role overrides (granular access)
  - Webhook      : Outbound webhook subscriptions
  - WebhookDelivery: Delivery log
  - SSOConfig    : SAML/OIDC SSO configuration per org
  - Notification  : Real-time notification queue
  - ProjectTemplate / TemplateTask: Project templates UI
  - SubcontractorRate: Subcontractor management
  - RevenueForeccast: Financial forecast snapshots
"""
from sqlalchemy import (
    Column, String, Float, DateTime, ForeignKey, Text,
    Boolean, Integer, Enum, Date
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
import uuid
from app.db.base import Base
from app.core.config import settings


# ── Audit Log ─────────────────────────────────────────────────────────────────

class AuditLog(Base):
    """
    Immutable audit trail. Written on every CREATE/UPDATE/DELETE across the app.
    Never deleted, never updated — append-only.
    """
    __tablename__ = "audit_logs"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    # Who
    user_id     = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    user_name   = Column(String(255), nullable=True)   # snapshot to survive user deletion
    ip_address  = Column(String(45), nullable=True)
    user_agent  = Column(String(500), nullable=True)

    # What
    action      = Column(String(50), nullable=False, index=True)   # CREATE UPDATE DELETE LOGIN LOGOUT EXPORT
    resource    = Column(String(100), nullable=False, index=True)  # projects tasks users expenses ...
    resource_id = Column(String(36), nullable=True, index=True)
    resource_name = Column(String(255), nullable=True)             # human-readable snapshot

    # Detail
    old_values  = Column(Text, nullable=True)   # JSON of changed fields before
    new_values  = Column(Text, nullable=True)   # JSON of changed fields after
    metadata_   = Column("metadata", Text, nullable=True)  # extra context JSON

    # When
    created_at  = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    user = relationship("User", foreign_keys=[user_id])


# ── Per-project permissions ───────────────────────────────────────────────────

class ProjectPermissionLevel(str, enum.Enum):
    none     = "none"      # Explicitly blocked
    viewer   = "viewer"    # Read-only — see tasks, timelines, no financials
    member   = "member"    # Can log work, create tasks
    manager  = "manager"   # PM-level: edit project, see financials
    owner    = "owner"     # Full control including delete


class ProjectPermission(Base):
    """
    Per-project permission override for a user.
    Supersedes the user's global role for this specific project.
    """
    __tablename__ = "project_permissions"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id   = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id      = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    level        = Column(Enum(ProjectPermissionLevel), nullable=False, default=ProjectPermissionLevel.member)
    can_see_financials = Column(Boolean, default=False)   # Costs, rates, budgets
    can_see_rates      = Column(Boolean, default=False)   # Hourly rates of teammates
    can_export         = Column(Boolean, default=True)
    granted_by   = Column(String(36), ForeignKey("users.id"), nullable=True)
    granted_at   = Column(DateTime(timezone=True), server_default=func.now())
    expires_at   = Column(DateTime(timezone=True), nullable=True)  # Temporary access
    note         = Column(String(500), nullable=True)

    project = relationship("Project")
    user    = relationship("User", foreign_keys=[user_id])
    granter = relationship("User", foreign_keys=[granted_by])


# ── Webhooks ──────────────────────────────────────────────────────────────────

class WebhookEvent(str, enum.Enum):
    project_created      = "project.created"
    project_updated      = "project.updated"
    project_closed       = "project.closed"
    task_created         = "task.created"
    task_status_changed  = "task.status_changed"
    task_assigned        = "task.assigned"
    sprint_started       = "sprint.started"
    sprint_closed        = "sprint.closed"
    expense_submitted    = "expense.submitted"
    expense_approved     = "expense.approved"
    ticket_created       = "ticket.created"
    ticket_resolved      = "ticket.resolved"
    timesheet_submitted  = "timesheet.submitted"
    timesheet_approved   = "timesheet.approved"
    risk_created         = "risk.created"


class Webhook(Base):
    """Outbound webhook subscription."""
    __tablename__ = "webhooks"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name        = Column(String(255), nullable=False)
    url         = Column(String(1000), nullable=False)
    secret      = Column(String(255), nullable=True)   # HMAC signing secret
    events      = Column(Text, nullable=False)          # JSON array of WebhookEvent
    is_active   = Column(Boolean, default=True)
    project_id  = Column(String(36), ForeignKey("projects.id"), nullable=True)  # None = all projects

    # Stats
    total_deliveries = Column(Integer, default=0)
    failed_deliveries = Column(Integer, default=0)
    last_triggered_at = Column(DateTime(timezone=True), nullable=True)

    created_by  = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())

    deliveries = relationship("WebhookDelivery", back_populates="webhook",
                              cascade="all, delete-orphan",
                              order_by="WebhookDelivery.created_at.desc()")
    creator  = relationship("User", foreign_keys=[created_by])
    project  = relationship("Project")


class WebhookDelivery(Base):
    """Log of each webhook delivery attempt."""
    __tablename__ = "webhook_deliveries"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    webhook_id  = Column(String(36), ForeignKey("webhooks.id", ondelete="CASCADE"), nullable=False, index=True)
    event       = Column(String(100), nullable=False)
    payload     = Column(Text, nullable=True)           # JSON sent
    status_code = Column(Integer, nullable=True)
    response    = Column(Text, nullable=True)
    success     = Column(Boolean, default=False)
    error       = Column(String(500), nullable=True)
    attempt     = Column(Integer, default=1)
    duration_ms = Column(Integer, nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())

    webhook = relationship("Webhook", back_populates="deliveries")


# ── SSO Configuration ─────────────────────────────────────────────────────────

class SSOProvider(str, enum.Enum):
    saml    = "saml"
    oidc    = "oidc"
    google  = "google"
    azure   = "azure_ad"
    okta    = "okta"


class SSOConfig(Base):
    """SSO/SAML/OIDC configuration."""
    __tablename__ = "sso_configs"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    provider    = Column(Enum(SSOProvider), nullable=False)
    is_active   = Column(Boolean, default=False)
    is_default  = Column(Boolean, default=False)   # Auto-redirect to SSO on login page

    # SAML
    saml_entity_id       = Column(String(500), nullable=True)
    saml_sso_url         = Column(String(500), nullable=True)
    saml_slo_url         = Column(String(500), nullable=True)
    saml_certificate     = Column(Text, nullable=True)
    saml_attribute_email = Column(String(200), default="email")
    saml_attribute_name  = Column(String(200), default="displayName")
    saml_attribute_role  = Column(String(200), nullable=True)

    # OIDC / OAuth2
    oidc_client_id       = Column(String(500), nullable=True)
    oidc_client_secret   = Column(String(500), nullable=True)
    oidc_discovery_url   = Column(String(500), nullable=True)
    oidc_scopes          = Column(String(500), default="openid email profile")

    # Role mapping from SSO groups to Clarive roles
    role_mapping         = Column(Text, nullable=True)  # JSON: {"SSO_GROUP": "pm", ...}
    organization_id      = Column(String(36), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True)

    # Auto-provisioning
    auto_create_users    = Column(Boolean, default=True)
    default_role         = Column(String(50), default="employee")
    allowed_domains      = Column(String(500), nullable=True)  # comma-separated

    created_by  = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())

    organization = relationship("Organization", foreign_keys=[organization_id])


# ── In-app Notifications ──────────────────────────────────────────────────────

class NotificationType(str, enum.Enum):
    task_assigned        = "task_assigned"
    task_mentioned       = "task_mentioned"
    task_due_soon        = "task_due_soon"
    task_overdue         = "task_overdue"
    sprint_started       = "sprint_started"
    sprint_ending        = "sprint_ending"
    expense_approved     = "expense_approved"
    expense_rejected     = "expense_rejected"
    ticket_assigned      = "ticket_assigned"
    ticket_replied       = "ticket_replied"
    ticket_resolved      = "ticket_resolved"
    project_risk_high    = "project_risk_high"
    timesheet_reminder   = "timesheet_reminder"
    timesheet_approved   = "timesheet_approved"
    budget_warning       = "budget_warning"
    mention              = "mention"
    automation           = "automation"
    system               = "system"


class Notification(Base):
    """In-app notification for a user."""
    __tablename__ = "notifications"

    id            = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id       = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    type          = Column(Enum(NotificationType), nullable=False, index=True)
    title         = Column(String(255), nullable=False)
    body          = Column(String(1000), nullable=True)
    icon          = Column(String(10), default="🔔")
    color         = Column(String(20), default="#00d4ff")

    # Link back to the resource
    resource      = Column(String(100), nullable=True)   # projects tasks tickets ...
    resource_id   = Column(String(36), nullable=True)
    action_url    = Column(String(500), nullable=True)   # frontend route

    is_read       = Column(Boolean, default=False, index=True)
    read_at       = Column(DateTime(timezone=True), nullable=True)
    created_at    = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    user = relationship("User", foreign_keys=[user_id])


# ── Subcontractors ────────────────────────────────────────────────────────────

class Subcontractor(Base):
    """External supplier / freelancer / subcontractor company."""
    __tablename__ = "subcontractors"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    code        = Column(String(20), nullable=False)      # SUB-001
    name        = Column(String(255), nullable=False)
    company     = Column(String(255), nullable=True)
    email       = Column(String(255), nullable=True)
    phone       = Column(String(50), nullable=True)
    country     = Column(String(100), nullable=True)
    vat_number  = Column(String(50), nullable=True)
    currency    = Column(String(3), default=settings.DEFAULT_CURRENCY)
    is_active   = Column(Boolean, default=True)
    notes       = Column(Text, nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())

    rates       = relationship("SubcontractorRate", back_populates="subcontractor",
                               cascade="all, delete-orphan")
    assignments = relationship("SubcontractorAssignment", back_populates="subcontractor")
    workers     = relationship("SubcontractorWorker", back_populates="subcontractor",
                               cascade="all, delete-orphan")


class SubcontractorRate(Base):
    """Rate card for a subcontractor (can vary by project/skill)."""
    __tablename__ = "subcontractor_rates"

    id               = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    subcontractor_id = Column(String(36), ForeignKey("subcontractors.id", ondelete="CASCADE"), nullable=False)
    description      = Column(String(255), nullable=False)   # "Senior Dev", "DevOps", etc
    cost_rate        = Column(Float, nullable=False)          # What we pay them €/h
    sell_rate        = Column(Float, nullable=True)           # What we charge client €/h
    currency         = Column(String(3), default=settings.DEFAULT_CURRENCY)
    valid_from       = Column(Date, nullable=True)
    valid_until      = Column(Date, nullable=True)

    subcontractor = relationship("Subcontractor", back_populates="rates")


class SubcontractorWorker(Base):
    """Individual person provided by a subcontractor company."""
    __tablename__ = "subcontractor_workers"

    id               = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    subcontractor_id = Column(String(36), ForeignKey("subcontractors.id", ondelete="CASCADE"), nullable=False, index=True)
    # Linked User record (resource) created automatically on worker creation
    user_id          = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    name             = Column(String(255), nullable=False)
    role             = Column(String(100), nullable=True)    # "Senior Developer", "DevOps Engineer"
    email            = Column(String(255), nullable=True)
    phone            = Column(String(50), nullable=True)
    cost_rate        = Column(Float, nullable=True)          # €/h we pay them
    sell_rate        = Column(Float, nullable=True)          # €/h we charge client
    currency         = Column(String(3), default=settings.DEFAULT_CURRENCY)
    available_from   = Column(Date, nullable=True)
    available_until  = Column(Date, nullable=True)
    weekly_capacity_hours = Column(Float, nullable=True)     # Hours/week capacity (default 40)
    is_active        = Column(Boolean, default=True)
    notes            = Column(Text, nullable=True)
    created_at       = Column(DateTime(timezone=True), server_default=func.now())
    updated_at       = Column(DateTime(timezone=True), onupdate=func.now())

    subcontractor = relationship("Subcontractor", back_populates="workers")
    user          = relationship("User", foreign_keys=[user_id])
    skills        = relationship("SubcontractorWorkerSkill", back_populates="worker",
                                 cascade="all, delete-orphan")
    assignments   = relationship("SubcontractorAssignment", back_populates="worker")


class SubcontractorWorkerSkill(Base):
    """Skill assignment for a subcontractor worker."""
    __tablename__ = "subcontractor_worker_skills"

    id               = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    worker_id        = Column(String(36), ForeignKey("subcontractor_workers.id", ondelete="CASCADE"), nullable=False, index=True)
    skill_id         = Column(String(36), ForeignKey("skills.id", ondelete="CASCADE"), nullable=False)
    level            = Column(String(20), nullable=False, default="intermediate")  # basic/intermediate/advanced/expert
    years_experience = Column(Float, nullable=True)
    certified        = Column(Boolean, default=False)
    cert_name        = Column(String(255), nullable=True)
    notes            = Column(String(255), nullable=True)
    created_at       = Column(DateTime(timezone=True), server_default=func.now())

    worker = relationship("SubcontractorWorker", back_populates="skills")
    skill  = relationship("Skill")


class SubcontractorAssignment(Base):
    """Assignment of a subcontractor to a project."""
    __tablename__ = "subcontractor_assignments"

    id               = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    subcontractor_id = Column(String(36), ForeignKey("subcontractors.id"), nullable=False, index=True)
    worker_id        = Column(String(36), ForeignKey("subcontractor_workers.id"), nullable=True, index=True)
    project_id       = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    rate_id          = Column(String(36), ForeignKey("subcontractor_rates.id"), nullable=True)
    po_number        = Column(String(100), nullable=True)    # Purchase Order
    po_amount        = Column(Float, nullable=True)          # PO ceiling €
    hours_contracted = Column(Float, nullable=True)
    hours_logged     = Column(Float, default=0)
    start_date       = Column(Date, nullable=True)
    end_date         = Column(Date, nullable=True)
    notes            = Column(Text, nullable=True)
    created_at       = Column(DateTime(timezone=True), server_default=func.now())

    subcontractor = relationship("Subcontractor", back_populates="assignments")
    worker        = relationship("SubcontractorWorker", back_populates="assignments")
    project       = relationship("Project")
    rate          = relationship("SubcontractorRate")


class SubcontractorInvoice(Base):
    """Factura recibida de un subcontratista (coste a registrar)."""
    __tablename__ = "subcontractor_invoices"

    id               = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    subcontractor_id = Column(String(36), ForeignKey("subcontractors.id", ondelete="CASCADE"), nullable=False, index=True)
    assignment_id    = Column(String(36), ForeignKey("subcontractor_assignments.id"), nullable=True)
    invoice_number   = Column(String(100), nullable=False)
    issue_date       = Column(Date, nullable=False)
    due_date         = Column(Date, nullable=True)
    amount           = Column(Float, nullable=False)          # subtotal sin IVA
    tax_pct          = Column(Float, default=settings.DEFAULT_TAX_RATE)
    total            = Column(Float, nullable=False)          # con IVA
    currency         = Column(String(3), default=settings.DEFAULT_CURRENCY)
    status           = Column(String(20), default="received") # received | approved | paid | rejected
    paid_date        = Column(Date, nullable=True)
    description      = Column(Text, nullable=True)
    file_path        = Column(String(500), nullable=True)     # adjunto PDF
    created_at       = Column(DateTime(timezone=True), server_default=func.now())

    subcontractor = relationship("Subcontractor")
    assignment    = relationship("SubcontractorAssignment")


class SubcontractorTimeLog(Base):
    """Registro de horas trabajadas por un subcontratista en un proyecto."""
    __tablename__ = "subcontractor_timelogs"

    id               = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    assignment_id    = Column(String(36), ForeignKey("subcontractor_assignments.id", ondelete="CASCADE"), nullable=False, index=True)
    subcontractor_id = Column(String(36), ForeignKey("subcontractors.id"), nullable=False, index=True)
    project_id       = Column(String(36), ForeignKey("projects.id"), nullable=True)
    log_date         = Column(Date, nullable=False)
    hours            = Column(Float, nullable=False)
    description      = Column(String(500), nullable=True)
    task_reference   = Column(String(100), nullable=True)     # referencia a tarea o entregable
    cost_amount      = Column(Float, nullable=True)           # horas × coste_tarifa
    is_invoiced      = Column(Boolean, default=False)         # incluido en alguna factura
    invoice_id       = Column(String(36), ForeignKey("subcontractor_invoices.id"), nullable=True)
    created_at       = Column(DateTime(timezone=True), server_default=func.now())

    assignment    = relationship("SubcontractorAssignment")
    subcontractor = relationship("Subcontractor")
    project       = relationship("Project")


# ── Revenue Forecast ──────────────────────────────────────────────────────────

class RevenueForecast(Base):
    """
    Monthly revenue & margin forecast per project.
    Updated when milestones change, project status changes, or manually.
    """
    __tablename__ = "revenue_forecasts"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id   = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    year         = Column(Integer, nullable=False, index=True)
    month        = Column(Integer, nullable=False)        # 1-12

    # Revenue
    revenue_planned  = Column(Float, default=0)   # What we expect to bill
    revenue_actual   = Column(Float, default=0)   # What we actually billed/recognized
    revenue_forecast = Column(Float, default=0)   # Best current estimate

    # Cost
    cost_planned  = Column(Float, default=0)
    cost_actual   = Column(Float, default=0)

    # Hours
    hours_planned = Column(Float, default=0)
    hours_actual  = Column(Float, default=0)

    # Margin
    margin_pct    = Column(Float, nullable=True)  # Computed: (revenue-cost)/revenue

    notes         = Column(String(500), nullable=True)
    updated_at    = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    project = relationship("Project")
