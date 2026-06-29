"""
v14 models — all P2 pending items:
  CABVote / MaintenanceWindow  : Change Management CAB flow
  WebhookTrigger               : External webhook triggers
  EmailTemplate / EmailLog     : SMTP email actions
  GDPRRequest                  : Right to erasure + data export
  IntegrationConfig            : GitHub/GitLab/Jira/Calendar/QuickBooks connectors
  CommitLink                   : Task ↔ commit/PR links
  RevenueRecognitionRule/Entry : ASC 606 / IFRS 15
  DashboardWidget              : Per-user dashboard personalisation
  OnboardingState              : Onboarding wizard progress
  ProjectRiskScore             : ML-style risk prediction per project
"""
from sqlalchemy import (
    Column, String, Float, DateTime, ForeignKey, Text,
    Boolean, Integer, Enum, Date
)
from app.models.money import Money
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
import uuid
from app.db.base import Base


# ── CAB (Change Advisory Board) ───────────────────────────────────────────────

class CABVote(Base):
    """Vote cast by a CAB member on a change request."""
    __tablename__ = "cab_votes"

    id               = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    change_request_id = Column(String(36), ForeignKey("change_requests.id", ondelete="CASCADE"),
                               nullable=False, index=True)
    voter_id         = Column(String(36), ForeignKey("users.id"), nullable=False)
    vote             = Column(String(10), nullable=False)  # approve | reject | abstain
    comment          = Column(Text, nullable=True)
    voted_at         = Column(DateTime(timezone=True), server_default=func.now())

    change_request = relationship("ChangeRequest")
    voter          = relationship("User", foreign_keys=[voter_id])


class MaintenanceWindow(Base):
    """Scheduled maintenance windows for change implementation."""
    __tablename__ = "maintenance_windows"

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    name        = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    start_dt    = Column(DateTime(timezone=True), nullable=False, index=True)
    end_dt      = Column(DateTime(timezone=True), nullable=False)
    environment = Column(String(50), default="production")  # production | staging | all
    is_recurring = Column(Boolean, default=False)
    recurrence  = Column(String(50), nullable=True)  # weekly_sunday_02am etc.
    created_by  = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())

    creator     = relationship("User", foreign_keys=[created_by])
    # Link to change requests scheduled in this window
    changes     = relationship("ChangeRequestWindow", back_populates="window",
                               cascade="all, delete-orphan")


class ChangeRequestWindow(Base):
    """Links a change request to a maintenance window."""
    __tablename__ = "change_request_windows"

    id                 = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    change_request_id  = Column(String(36), ForeignKey("change_requests.id", ondelete="CASCADE"),
                                nullable=False, index=True)
    window_id          = Column(String(36), ForeignKey("maintenance_windows.id", ondelete="CASCADE"),
                                nullable=False, index=True)
    rollback_plan      = Column(Text, nullable=True)
    test_plan          = Column(Text, nullable=True)
    created_at         = Column(DateTime(timezone=True), server_default=func.now())

    window         = relationship("MaintenanceWindow", back_populates="changes")
    change_request = relationship("ChangeRequest")


# ── Webhook Triggers (incoming) ───────────────────────────────────────────────

class WebhookTrigger(Base):
    """Incoming webhook endpoint that fires a workflow."""
    __tablename__ = "webhook_triggers"

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    name        = Column(String(255), nullable=False)
    slug        = Column(String(100), nullable=False, unique=True, index=True)  # URL key
    slug_rotated_at = Column(DateTime(timezone=True), nullable=True)
    slug_expires_at = Column(DateTime(timezone=True), nullable=True)
    secret      = Column(String(255), nullable=True)    # HMAC secret for verification
    workflow_id = Column(String(36), ForeignKey("automation_workflows.id"), nullable=True)
    rule_id     = Column(String(36), ForeignKey("automation_rules.id"), nullable=True)
    is_active   = Column(Boolean, default=True)
    last_fired_at = Column(DateTime(timezone=True), nullable=True)
    fire_count  = Column(Integer, default=0)
    # Field mapping: how to map incoming JSON to trigger context
    field_mapping = Column(Text, nullable=True)  # JSON: {"project_id": "$.project.id"}
    created_by  = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())

    workflow = relationship("AutomationWorkflow")
    creator  = relationship("User", foreign_keys=[created_by])


class WebhookTriggerLog(Base):
    """Log of every incoming webhook call."""
    __tablename__ = "webhook_trigger_logs"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    trigger_id  = Column(String(36), ForeignKey("webhook_triggers.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    payload     = Column(Text, nullable=True)       # JSON body received
    headers     = Column(Text, nullable=True)       # JSON relevant headers
    status      = Column(String(20), default="ok")  # ok | error | unauthorized
    error       = Column(String(500), nullable=True)
    received_at = Column(DateTime(timezone=True), server_default=func.now())

    trigger = relationship("WebhookTrigger")


# ── Email Templates & Logs ────────────────────────────────────────────────────

class EmailTemplate(Base):
    """Reusable HTML email templates for automation actions (per tenant)."""
    __tablename__ = "email_templates"

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    name        = Column(String(255), nullable=False)
    subject     = Column(String(500), nullable=False)
    body_html   = Column(Text, nullable=False)    # Jinja2-compatible HTML
    body_text   = Column(Text, nullable=True)     # Plain text fallback
    category    = Column(String(50), default="automation")  # automation|alert|report|invoice
    variables   = Column(Text, nullable=True)     # JSON: list of available {{variables}}
    is_system   = Column(Boolean, default=False)
    created_by  = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())

    creator = relationship("User", foreign_keys=[created_by])


class EmailLog(Base):
    """Audit trail for every email sent by the system."""
    __tablename__ = "email_logs"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    to_address   = Column(String(255), nullable=False, index=True)
    cc_addresses = Column(Text, nullable=True)    # JSON array
    subject      = Column(String(500), nullable=False)
    template_id  = Column(String(36), ForeignKey("email_templates.id"), nullable=True)
    body_preview = Column(String(500), nullable=True)  # First 500 chars
    status       = Column(String(20), default="queued")  # queued|sent|failed|bounced
    error        = Column(String(500), nullable=True)
    sent_at      = Column(DateTime(timezone=True), nullable=True)
    opened_at    = Column(DateTime(timezone=True), nullable=True)
    source       = Column(String(50), nullable=True)  # automation|report|invoice|alert
    source_id    = Column(String(36), nullable=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

    template = relationship("EmailTemplate")


# ── GDPR ──────────────────────────────────────────────────────────────────────

class GDPRRequestType(str, enum.Enum):
    erasure = "erasure"        # Art. 17 — right to be forgotten
    portability = "portability"  # Art. 20 — data export
    access = "access"          # Art. 15 — access to personal data
    rectification = "rectification"  # Art. 16


class GDPRRequestStatus(str, enum.Enum):
    pending    = "pending"
    processing = "processing"
    completed  = "completed"
    rejected   = "rejected"


class GDPRRequest(Base):
    """GDPR data subject request tracking."""
    __tablename__ = "gdpr_requests"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    request_type = Column(Enum(GDPRRequestType), nullable=False, index=True)
    subject_user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    subject_email = Column(String(255), nullable=True)  # For deleted users
    requestor_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    status       = Column(Enum(GDPRRequestStatus), default=GDPRRequestStatus.pending)
    notes        = Column(Text, nullable=True)
    # For portability: link to generated export file
    export_url   = Column(String(500), nullable=True)
    export_data  = Column(Text, nullable=True)  # JSON summary of exported/anonymised fields
    deadline     = Column(Date, nullable=True)   # 30 days from request
    completed_at = Column(DateTime(timezone=True), nullable=True)
    processed_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

    subject_user  = relationship("User", foreign_keys=[subject_user_id])
    requestor     = relationship("User", foreign_keys=[requestor_id])
    processor     = relationship("User", foreign_keys=[processed_by])


# ── External Integrations ─────────────────────────────────────────────────────

class IntegrationType(str, enum.Enum):
    github     = "github"
    gitlab     = "gitlab"
    jira       = "jira"
    google_calendar = "google_calendar"
    outlook    = "outlook"
    quickbooks = "quickbooks"
    xero       = "xero"
    slack      = "slack"
    teams      = "teams"


class IntegrationConfig(Base):
    """OAuth/API config for external service integrations (per tenant)."""
    __tablename__ = "integration_configs"

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    integration_type = Column(Enum(IntegrationType), nullable=False, index=True)
    name            = Column(String(255), nullable=False)
    is_active       = Column(Boolean, default=True)

    # Auth (stored encrypted in production)
    access_token    = Column(Text, nullable=True)
    refresh_token   = Column(Text, nullable=True)
    token_expires_at = Column(DateTime(timezone=True), nullable=True)

    # Config (JSON: org_name, repo, project_key, calendar_id, etc.)
    config          = Column(Text, nullable=True)

    # Sync state
    last_sync_at    = Column(DateTime(timezone=True), nullable=True)
    sync_errors     = Column(Integer, default=0)
    last_error      = Column(String(500), nullable=True)

    created_by      = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    updated_at      = Column(DateTime(timezone=True), onupdate=func.now())

    creator = relationship("User", foreign_keys=[created_by])


class CommitLink(Base):
    """Links a git commit or PR to a Contecflow task."""
    __tablename__ = "commit_links"

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    task_id         = Column(String(36), ForeignKey("tasks.id", ondelete="CASCADE"),
                             nullable=False, index=True)
    integration_id  = Column(String(36), ForeignKey("integration_configs.id"), nullable=True)
    link_type       = Column(String(20), default="commit")  # commit | pr | branch | issue
    external_id     = Column(String(255), nullable=True)    # SHA / PR number
    title           = Column(String(500), nullable=True)
    url             = Column(String(1000), nullable=True)
    author          = Column(String(255), nullable=True)
    state           = Column(String(20), nullable=True)     # open | merged | closed
    created_at_ext  = Column(DateTime(timezone=True), nullable=True)  # Date in git system
    synced_at       = Column(DateTime(timezone=True), server_default=func.now())

    task        = relationship("Task")
    integration = relationship("IntegrationConfig")


class CalendarEvent(Base):
    """Synced calendar event from Google Calendar or Outlook."""
    __tablename__ = "calendar_events"

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    integration_id  = Column(String(36), ForeignKey("integration_configs.id"), nullable=True)
    external_id     = Column(String(255), nullable=True, index=True)  # Google/Outlook event ID
    user_id         = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    title           = Column(String(500), nullable=False)
    start_dt        = Column(DateTime(timezone=True), nullable=False, index=True)
    end_dt          = Column(DateTime(timezone=True), nullable=False)
    all_day         = Column(Boolean, default=False)
    description     = Column(Text, nullable=True)
    location        = Column(String(500), nullable=True)
    # Links to Contecflow objects
    project_id      = Column(String(36), ForeignKey("projects.id"), nullable=True)
    sprint_id       = Column(String(36), ForeignKey("sprints.id"), nullable=True)
    milestone_id    = Column(String(36), ForeignKey("project_milestones.id"), nullable=True)
    sync_direction  = Column(String(10), default="pull")  # pull | push | both
    last_synced_at  = Column(DateTime(timezone=True), server_default=func.now())

    integration = relationship("IntegrationConfig")
    user        = relationship("User", foreign_keys=[user_id])
    project     = relationship("Project")


# ── Revenue Recognition (ASC 606 / IFRS 15) ──────────────────────────────────

class RecognitionMethod(str, enum.Enum):
    percentage_complete = "percentage_complete"  # % of work done
    milestone           = "milestone"            # On milestone achieved
    milestone_billing   = "milestone_billing"    # Basado en milestones aprobados/facturados
    time_and_material   = "time_and_material"    # As hours are logged
    straight_line       = "straight_line"        # Evenly over contract period
    completed_contract  = "completed_contract"   # Only at project close


class RevenueRecognitionRule(Base):
    """Per-project revenue recognition configuration."""
    __tablename__ = "revenue_recognition_rules"

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    project_id      = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"),
                             nullable=False, unique=True, index=True)
    method          = Column(Enum(RecognitionMethod),
                             default=RecognitionMethod.percentage_complete)
    contract_value  = Column(Money, nullable=True)   # Total contract amount
    start_date      = Column(Date, nullable=True)
    end_date        = Column(Date, nullable=True)
    notes           = Column(Text, nullable=True)
    created_by      = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    updated_at      = Column(DateTime(timezone=True), onupdate=func.now())

    project = relationship("Project")
    entries = relationship("RevenueRecognitionEntry", back_populates="rule",
                          cascade="all, delete-orphan",
                          order_by="RevenueRecognitionEntry.period_date")
    creator = relationship("User", foreign_keys=[created_by])


class RevenueRecognitionEntry(Base):
    """Monthly revenue recognition entry (one per period per project)."""
    __tablename__ = "revenue_recognition_entries"

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    rule_id         = Column(String(36), ForeignKey("revenue_recognition_rules.id",
                             ondelete="CASCADE"), nullable=False, index=True)
    project_id      = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    period_date     = Column(Date, nullable=False, index=True)  # First day of month
    pct_complete    = Column(Float, default=0)       # % of project complete this period
    amount_planned  = Column(Money, default=0)       # Revenue planned to recognise
    amount_actual   = Column(Money, default=0)       # Revenue actually recognised
    amount_deferred = Column(Money, default=0)       # Deferred to future periods
    cumulative_pct  = Column(Float, default=0)       # % ratio
    cumulative_amount = Column(Money, default=0)
    is_locked       = Column(Boolean, default=False)  # Locked after accounting close
    notes           = Column(Text, nullable=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())

    rule    = relationship("RevenueRecognitionRule", back_populates="entries")
    project = relationship("Project")


# ── Dashboard Widgets (personalisation) ──────────────────────────────────────

class DashboardWidget(Base):
    """Per-user dashboard widget configuration."""
    __tablename__ = "dashboard_widgets"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    user_id     = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    widget_type = Column(String(50), nullable=False)   # kpi_hours | chart_margin | list_tasks...
    title       = Column(String(255), nullable=True)
    position_x  = Column(Integer, default=0)           # Grid column (0-3)
    position_y  = Column(Integer, default=0)           # Grid row
    width       = Column(Integer, default=1)            # 1 | 2 | 3 | 4 columns
    height      = Column(Integer, default=1)            # 1 | 2 rows
    config      = Column(Text, nullable=True)           # JSON: filters, chart_type, etc.
    is_visible  = Column(Boolean, default=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", foreign_keys=[user_id])


# ── Onboarding Wizard ─────────────────────────────────────────────────────────

class OnboardingState(Base):
    """Tracks onboarding wizard progress for each user."""
    __tablename__ = "onboarding_states"

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    user_id         = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"),
                             nullable=False, unique=True, index=True)
    current_step    = Column(Integer, default=0)       # 0=not started, 5=complete
    completed_steps = Column(Text, default="[]")       # JSON: list of completed step IDs
    is_complete     = Column(Boolean, default=False)
    dismissed_at    = Column(DateTime(timezone=True), nullable=True)  # If user skipped
    started_at      = Column(DateTime(timezone=True), server_default=func.now())
    completed_at    = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", foreign_keys=[user_id])


# ── Project Risk Score (prediction) ──────────────────────────────────────────

class ProjectRiskScore(Base):
    """Computed risk score and prediction for a project."""
    __tablename__ = "project_risk_scores"

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    project_id      = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"),
                             nullable=False, index=True)
    computed_at     = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    # Score components (0-100)
    schedule_risk   = Column(Float, default=0)   # Late delivery risk
    budget_risk     = Column(Float, default=0)   # Budget overrun risk
    resource_risk   = Column(Float, default=0)   # Key person dependency / overload
    scope_risk      = Column(Float, default=0)   # Number of open change requests
    overall_score   = Column(Float, default=0)   # Weighted composite (0-100)

    # Prediction
    delay_probability_pct = Column(Float, default=0)   # % chance of > 2 week delay
    predicted_delay_weeks = Column(Float, nullable=True)
    predicted_overrun_pct = Column(Float, nullable=True)  # Budget overrun %

    # Context used to compute
    pct_complete    = Column(Float, nullable=True)
    days_elapsed_pct = Column(Float, nullable=True)
    budget_consumed_pct = Column(Float, nullable=True)
    open_risks_count = Column(Integer, default=0)
    open_cr_count   = Column(Integer, default=0)
    overloaded_members = Column(Integer, default=0)

    level           = Column(String(10), default="low")  # low | medium | high | critical
    recommendation  = Column(Text, nullable=True)

    project = relationship("Project")
