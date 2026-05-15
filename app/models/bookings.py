"""
bookings models — completing all 'Partial' items from the roadmap:
  - TaskDependency    : Task dependencies for Gantt (FS, SS, SF, FF)
  - ResourceBooking   : Soft/hard bookings for resource planning
  - ExchangeRate      : Currency exchange rates table
  - SLASchedule       : Business hours + holiday calendars for SLA
  - ApiKey            : Client API keys with rate limiting
  - RecurringInvoice  : Recurring invoice configuration
  - WorkflowQueue     : Execution queue for multi-step workflows
  - OAuthState        : SSO SAML/OIDC state + session management
"""
from sqlalchemy import (
    Column, String, Float, DateTime, ForeignKey, Text,
    Boolean, Integer, Enum, Date, Time
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
import uuid
from app.db.base import Base
from app.core.config import settings


# ── Task Dependencies ─────────────────────────────────────────────────────────

class DependencyType(str, enum.Enum):
    finish_to_start  = "FS"   # Task B starts after Task A finishes (most common)
    start_to_start   = "SS"   # Task B starts after Task A starts
    finish_to_finish = "FF"   # Task B finishes after Task A finishes
    start_to_finish  = "SF"   # Task B finishes after Task A starts (rare)


class TaskDependency(Base):
    """Dependency relationship between two tasks."""
    __tablename__ = "task_dependencies"

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    predecessor_id  = Column(String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    successor_id    = Column(String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    dependency_type = Column(Enum(DependencyType), default=DependencyType.finish_to_start, nullable=False)
    is_active       = Column(Boolean, default=True)
    lag_days        = Column(Integer, default=0)   # positive = delay, negative = overlap
    created_by      = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())

    predecessor = relationship("Task", foreign_keys=[predecessor_id])
    successor   = relationship("Task", foreign_keys=[successor_id])
    creator     = relationship("User", foreign_keys=[created_by])

    def __repr__(self) -> str:
        return f"<TaskDependency id={self.id!r} type={self.dependency_type!r}>"


# ── Resource Bookings ─────────────────────────────────────────────────────────

class BookingType(str, enum.Enum):
    hard = "hard"   # Confirmed — counts against capacity
    soft = "soft"   # Tentative — shown in heatmap but not blocking


class ResourceBooking(Base):
    """Explicit resource booking for capacity planning heatmap."""
    __tablename__ = "resource_bookings"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    user_id     = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id  = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    task_id     = Column(String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True)
    booking_type = Column(Enum(BookingType), default=BookingType.hard, nullable=False)

    start_date  = Column(Date, nullable=False, index=True)
    end_date    = Column(Date, nullable=False, index=True)
    hours_per_day = Column(Float, default=8.0)
    total_hours = Column(Float, nullable=True)   # computed: days * hours_per_day

    note        = Column(String(500), nullable=True)
    created_by  = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())
    is_active   = Column(Boolean, default=True)

    user    = relationship("User", foreign_keys=[user_id])
    project = relationship("Project")
    task    = relationship("Task")
    creator = relationship("User", foreign_keys=[created_by])

    def __repr__(self) -> str:
        return f"<ResourceBooking id={self.id!r} user_id={self.user_id!r}>"


# ── Exchange Rates ────────────────────────────────────────────────────────────

class ExchangeRate(Base):
    """Currency exchange rates against base currency (EUR by default)."""
    __tablename__ = "exchange_rates"

    id            = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    from_currency = Column(String(3), nullable=False, index=True)
    to_currency   = Column(String(3), nullable=False, index=True)
    rate          = Column(Float, nullable=False)        # 1 from_currency = rate to_currency
    effective_date = Column(Date, nullable=False, index=True)
    source        = Column(String(50), default="manual")  # manual | ecb | openexchange
    created_at    = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<ExchangeRate id={self.id!r} {self.from_currency}->{self.to_currency} rate={self.rate!r}>"


# ── SLA Business Hours Schedules ──────────────────────────────────────────────

class SLASchedule(Base):
    """Business hours schedule for SLA calculation (not 24/7)."""
    __tablename__ = "sla_schedules"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    name        = Column(String(255), nullable=False)    # "9-17 Mon-Fri", "24/7"
    timezone    = Column(String(50), default=settings.DEFAULT_TIMEZONE)
    is_default  = Column(Boolean, default=False)

    # Days of week (JSON array: [1,2,3,4,5] = Mon-Fri)
    work_days   = Column(Text, default='[1,2,3,4,5]')
    work_start  = Column(Time, nullable=True)             # e.g. 09:00
    work_end    = Column(Time, nullable=True)             # e.g. 17:00

    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    holidays    = relationship("SLAHoliday", back_populates="schedule",
                              cascade="all, delete-orphan")


class SLAHoliday(Base):
    """Holiday dates for a given SLA schedule."""
    __tablename__ = "sla_holidays"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    schedule_id = Column(String(36), ForeignKey("sla_schedules.id", ondelete="CASCADE"), nullable=False, index=True)
    date        = Column(Date, nullable=False)
    name        = Column(String(100), nullable=True)
    country     = Column(String(10), nullable=True)   # ISO country code

    schedule = relationship("SLASchedule", back_populates="holidays")


# ── API Keys ──────────────────────────────────────────────────────────────────

class ApiKey(Base):
    """Client API key for external integrations (not JWT-based)."""
    __tablename__ = "api_keys"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    name        = Column(String(255), nullable=False)    # "Slack integration", "BI dashboard"
    key_hash    = Column(String(255), nullable=False, unique=True)  # bcrypt hash of the key
    key_prefix  = Column(String(8), nullable=False)      # First 8 chars shown in UI: "nxpm_abc"
    user_id     = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    scopes      = Column(Text, default='["read"]')        # JSON: ["read", "write", "admin"]

    # Rate limiting
    rate_limit_per_hour  = Column(Integer, default=1000)
    rate_limit_per_day   = Column(Integer, default=10000)
    requests_today       = Column(Integer, default=0)
    requests_this_hour   = Column(Integer, default=0)
    last_used_at         = Column(DateTime(timezone=True), nullable=True)
    last_reset_at        = Column(DateTime(timezone=True), nullable=True)

    is_active   = Column(Boolean, default=True)
    expires_at  = Column(DateTime(timezone=True), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    last_seen   = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", foreign_keys=[user_id])

    def __repr__(self) -> str:
        return f"<ApiKey id={self.id!r} name={self.name!r}>"


# ── Recurring Invoices ────────────────────────────────────────────────────────

class RecurringFrequency(str, enum.Enum):
    weekly   = "weekly"
    monthly  = "monthly"
    quarterly = "quarterly"
    annually = "annually"


class RecurringInvoice(Base):
    """Configuration for automatically generated recurring invoices."""
    __tablename__ = "recurring_invoices"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    name        = Column(String(255), nullable=False)    # "Retainer mensual Acme"
    project_id  = Column(String(36), ForeignKey("projects.id"), nullable=True, index=True)
    contract_id = Column(String(36), ForeignKey("contracts.id"), nullable=True)

    frequency   = Column(Enum(RecurringFrequency), nullable=False, default=RecurringFrequency.monthly)
    next_date   = Column(Date, nullable=False)
    end_date    = Column(Date, nullable=True)    # None = no end
    is_active   = Column(Boolean, default=True)

    # Invoice template data
    client_name    = Column(String(255), nullable=True)
    client_email   = Column(String(255), nullable=True)
    client_vat     = Column(String(50), nullable=True)
    amount         = Column(Float, nullable=False)       # Fixed amount per period
    tax_rate       = Column(Float, default=settings.DEFAULT_TAX_RATE)
    currency       = Column(String(3), default=settings.DEFAULT_CURRENCY)
    description    = Column(String(500), nullable=True)  # Line item description
    payment_terms_days = Column(Integer, default=30)

    # Stats
    last_generated_at = Column(DateTime(timezone=True), nullable=True)
    total_generated   = Column(Integer, default=0)

    created_by  = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())

    project  = relationship("Project")
    contract = relationship("Contract")
    creator  = relationship("User", foreign_keys=[created_by])

    def __repr__(self) -> str:
        return f"<RecurringInvoice id={self.id!r} name={self.name!r}>"


# ── Workflow Queue (execution engine) ─────────────────────────────────────────

class WorkflowQueueItem(Base):
    """
    Queue item for the workflow execution engine.
    APScheduler polls this table and processes pending items.
    """
    __tablename__ = "workflow_queue"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    workflow_id  = Column(String(36), ForeignKey("automation_workflows.id", ondelete="CASCADE"), nullable=False, index=True)
    execution_id = Column(String(36), nullable=True)    # Links to WorkflowExecution
    step_index   = Column(Integer, default=0)
    status       = Column(String(20), default="pending", index=True)  # pending|processing|done|failed
    trigger_data = Column(Text, nullable=True)          # JSON context
    execute_at   = Column(DateTime(timezone=True), nullable=False, index=True)  # When to run (for waits)
    attempts     = Column(Integer, default=0)
    last_error   = Column(String(500), nullable=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
    processed_at = Column(DateTime(timezone=True), nullable=True)

    workflow = relationship("AutomationWorkflow")


# ── OAuth / SSO State ─────────────────────────────────────────────────────────

class OAuthState(Base):
    """
    Temporary state token for SAML/OIDC authentication flows.
    Created at redirect, consumed at callback.
    """
    __tablename__ = "oauth_states"

    id         = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    state      = Column(String(255), nullable=False, unique=True, index=True)
    sso_config_id = Column(String(36), ForeignKey("sso_configs.id", ondelete="CASCADE"), nullable=False)
    redirect_to = Column(String(500), default="/dashboard")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used       = Column(Boolean, default=False)

    sso_config = relationship("SSOConfig")
