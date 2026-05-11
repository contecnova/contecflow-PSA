from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Text, Boolean, Integer, Date
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.db.base import Base
from app.core.config import settings


# ── Custom Roles & Permissions ────────────────────────────────────────────────

class CustomRole(Base):
    """Custom roles with granular permissions."""
    __tablename__ = "custom_roles"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), unique=True, nullable=False)
    description = Column(String(255), nullable=True)
    color = Column(String(20), default="#7a8aaa")
    is_active = Column(Boolean, default=True)
    is_system = Column(Boolean, default=False)  # Cannot be deleted

    # Module access (JSON: {"dashboard": true, "projects": true, ...})
    module_access = Column(Text, nullable=True)  # JSON string

    # Feature permissions (JSON)
    permissions = Column(Text, nullable=True)  # JSON string

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


# ── Project Templates ─────────────────────────────────────────────────────────

class ProjectTemplate(Base):
    """Reusable project templates with predefined phases, tasks and deliverables."""
    __tablename__ = "project_templates"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    project_type = Column(String(50), nullable=True)
    estimated_weeks = Column(Integer, nullable=True)
    estimated_hours = Column(Float, nullable=True)
    is_active = Column(Boolean, default=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    creator = relationship("User", foreign_keys=[created_by])
    phases = relationship("TemplatePhase", back_populates="template", cascade="all, delete-orphan", order_by="TemplatePhase.order")
    risks = relationship("TemplateRisk", back_populates="template", cascade="all, delete-orphan")
    deliverables = relationship("TemplateDeliverable", back_populates="template", cascade="all, delete-orphan")


class TemplatePhase(Base):
    __tablename__ = "template_phases"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    template_id = Column(String(36), ForeignKey("project_templates.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    order = Column(Integer, default=0)
    estimated_weeks = Column(Integer, nullable=True)
    estimated_hours = Column(Float, nullable=True)

    template = relationship("ProjectTemplate", back_populates="phases")
    tasks = relationship("TemplateTask", back_populates="phase", cascade="all, delete-orphan", order_by="TemplateTask.order")


class TemplateTask(Base):
    __tablename__ = "template_tasks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    phase_id = Column(String(36), ForeignKey("template_phases.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    estimated_hours = Column(Float, nullable=True)
    skill_required = Column(String(100), nullable=True)
    order = Column(Integer, default=0)

    phase = relationship("TemplatePhase", back_populates="tasks")


class TemplateRisk(Base):
    __tablename__ = "template_risks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    template_id = Column(String(36), ForeignKey("project_templates.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=False)
    category = Column(String(50), nullable=True)
    probability = Column(String(20), default="medium")
    impact = Column(String(20), default="moderate")
    mitigation_plan = Column(Text, nullable=True)

    template = relationship("ProjectTemplate", back_populates="risks")


class TemplateDeliverable(Base):
    __tablename__ = "template_deliverables"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    template_id = Column(String(36), ForeignKey("project_templates.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    format = Column(String(100), nullable=True)
    acceptance_criteria = Column(Text, nullable=True)
    week_offset = Column(Integer, nullable=True)  # Weeks from project start
    billing_pct = Column(Float, nullable=True)

    template = relationship("ProjectTemplate", back_populates="deliverables")


# ── Task Types ────────────────────────────────────────────────────────────────

class TaskType(Base):
    __tablename__ = "task_types"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), unique=True, nullable=False)
    value = Column(String(50), unique=True, nullable=False)
    icon = Column(String(10), default="📋")
    color = Column(String(20), default="#7a8aaa")
    is_billable_default = Column(Boolean, default=True)
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ── Alert Configuration ───────────────────────────────────────────────────────

class AlertConfig(Base):
    """Configurable thresholds and recipients for each alert type."""
    __tablename__ = "alert_configs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    alert_type = Column(String(50), unique=True, nullable=False)
    label = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    is_enabled = Column(Boolean, default=True)

    # Threshold
    threshold_value = Column(Float, nullable=True)
    threshold_unit = Column(String(20), nullable=True)  # %, days, hours

    # Notification
    notify_admin = Column(Boolean, default=True)
    notify_pm = Column(Boolean, default=True)
    notify_hr = Column(Boolean, default=False)
    notify_employee = Column(Boolean, default=False)
    notify_email = Column(Boolean, default=False)

    # Severity
    severity = Column(String(20), default="warning")  # info, warning, critical

    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# ── Rate Tables ───────────────────────────────────────────────────────────────

class RateTable(Base):
    """Rate tables by role, department or client."""
    __tablename__ = "rate_tables"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    is_default = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    applies_to = Column(String(20), default="role")  # role | department | client
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    entries = relationship("RateEntry", back_populates="table", cascade="all, delete-orphan")


class RateEntry(Base):
    __tablename__ = "rate_entries"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    table_id     = Column(String(36), ForeignKey("rate_tables.id", ondelete="CASCADE"), nullable=False)
    label        = Column(String(100), nullable=False)   # nombre del rol/perfil
    cost_rate    = Column(Float, nullable=True)          # coste interno €/h
    billing_rate = Column(Float, nullable=True)          # tarifa cliente €/h
    currency     = Column(String(3), default=settings.DEFAULT_CURRENCY)
    valid_from   = Column(Date, nullable=True)
    valid_to     = Column(Date, nullable=True)
    escalation_pct = Column(Float, default=0.0)          # % escalado anual
    notes        = Column(String(255), nullable=True)
    is_active    = Column(Boolean, default=True)

    table = relationship("RateTable", back_populates="entries")


class RateOverride(Base):
    """Tarifa específica para un cliente o proyecto concreto (sobreescribe la tabla base)."""
    __tablename__ = "rate_overrides"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    table_id     = Column(String(36), ForeignKey("rate_tables.id", ondelete="CASCADE"), nullable=False)
    client_id    = Column(String(36), ForeignKey("clients.id",  ondelete="CASCADE"), nullable=True)
    project_id   = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    role_label   = Column(String(100), nullable=False)   # debe coincidir con RateEntry.label
    billing_rate = Column(Float, nullable=False)
    valid_from   = Column(Date, nullable=True)
    valid_to     = Column(Date, nullable=True)
    notes        = Column(String(255), nullable=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

    table   = relationship("RateTable")


# ── Vacation Policy ───────────────────────────────────────────────────────────

class VacationPolicy(Base):
    __tablename__ = "vacation_policies"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    days_per_year = Column(Float, default=settings.DEFAULT_VACATION_DAYS_PER_YEAR)
    accrual_type = Column(String(20), default="annual")  # annual | monthly
    carries_over = Column(Boolean, default=True)
    max_carryover_days = Column(Float, nullable=True)
    carryover_expiry_months = Column(Integer, nullable=True)
    applies_to_roles = Column(Text, nullable=True)  # JSON list of roles
    is_default = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class UserVacationBalance(Base):
    __tablename__ = "user_vacation_balances"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    year = Column(Integer, nullable=False)
    policy_id = Column(String(36), ForeignKey("vacation_policies.id"), nullable=True)
    days_entitled = Column(Float, default=settings.DEFAULT_VACATION_DAYS_PER_YEAR)
    days_taken = Column(Float, default=0)
    days_pending = Column(Float, default=0)  # Requested but not yet approved
    days_carried_over = Column(Float, default=0)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", foreign_keys=[user_id])
    policy = relationship("VacationPolicy")


# ── Office / Location Calendar ────────────────────────────────────────────────

class Office(Base):
    __tablename__ = "offices"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), nullable=False)
    country = Column(String(50), nullable=True)
    city = Column(String(100), nullable=True)
    timezone = Column(String(50), default=settings.DEFAULT_TIMEZONE)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ── Auto-numbering ────────────────────────────────────────────────────────────

class NumberingSequence(Base):
    __tablename__ = "numbering_sequences"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity = Column(String(50), unique=True, nullable=False)  # project, task, contract, etc.
    prefix = Column(String(20), default="")
    suffix = Column(String(20), default="")
    separator = Column(String(5), default="-")
    include_year = Column(Boolean, default=False)
    padding = Column(Integer, default=4)
    current_value = Column(Integer, default=0)
    reset_yearly = Column(Boolean, default=False)
    last_reset_year = Column(Integer, nullable=True)
    example = Column(String(50), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# ── Custom Fields ─────────────────────────────────────────────────────────────

class CustomField(Base):
    __tablename__ = "custom_fields"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity = Column(String(50), nullable=False, index=True)  # project, task, user
    name = Column(String(100), nullable=False)
    field_key = Column(String(50), nullable=False)  # snake_case key
    field_type = Column(String(20), nullable=False)  # text, number, date, select, boolean, url
    options = Column(Text, nullable=True)  # JSON for select options
    is_required = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    placeholder = Column(String(255), nullable=True)
    default_value = Column(String(255), nullable=True)
    visible_to_roles = Column(Text, nullable=True)  # JSON list
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CustomFieldValue(Base):
    __tablename__ = "custom_field_values"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    field_id = Column(String(36), ForeignKey("custom_fields.id", ondelete="CASCADE"), nullable=False)
    entity_id = Column(String(36), nullable=False, index=True)  # ID of the project/task/user
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    field = relationship("CustomField")
