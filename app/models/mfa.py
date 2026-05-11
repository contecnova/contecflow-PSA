"""
v15 models — all remaining pending features:
  Organization          : Multi-tenancy root — every entity belongs to an org
  MFAConfig             : TOTP/2FA per user
  MFABackupCode         : One-time backup codes for MFA
  SlackConfig           : Slack/Teams workspace connection
  SlackNotificationLog  : Audit of Slack messages sent
  Budget                : Multi-period department budgets
  BudgetEntry           : Monthly actuals vs planned per budget
  AITaskEstimate        : AI-suggested hour estimates for tasks
  AITicketTriage        : AI triage result per SD ticket
  ScenarioModel         : What-if capacity scenario
  ScenarioProject       : Simulated project inside a scenario
  PDFExportJob          : Queued/completed PDF export jobs
  BIToken               : BI connector tokens (Power BI / Tableau)
"""
from sqlalchemy import (
    Column, String, Float, DateTime, ForeignKey, Text,
    Boolean, Integer, Date
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.db.base import Base
from app.core.config import settings


# ── Multi-tenancy ─────────────────────────────────────────────────────────────

class Organization(Base):
    """Root tenant entity — every org has its own isolated data space."""
    __tablename__ = "organizations"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name         = Column(String(255), nullable=False)
    slug         = Column(String(100), nullable=False, unique=True, index=True)
    plan         = Column(String(20), default="starter")  # starter | pro | enterprise
    is_active    = Column(Boolean, default=True)
    max_users    = Column(Integer, default=25)
    max_projects = Column(Integer, default=100)
    logo_url     = Column(String(500), nullable=True)
    primary_color = Column(String(7), nullable=True)    # hex e.g. #1a73e8
    timezone     = Column(String(50), default=settings.DEFAULT_TIMEZONE)
    locale       = Column(String(10), default=settings.DEFAULT_LANGUAGE)
    admin_email  = Column(String(255), nullable=True)
    imputation_lockout_days = Column(Integer, default=settings.DEFAULT_IMPUTATION_LOCKOUT_DAYS)  # Days before imputations are locked
    # Política de seguridad: si está activa, todos los usuarios de esta
    # organización deben tener MFA habilitada para poder completar el login.
    # Aplicado en auth_core.py durante el flujo de password+MFA.
    require_mfa  = Column(Boolean, default=False, nullable=False, server_default="0")
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
    updated_at   = Column(DateTime(timezone=True), onupdate=func.now())

    users    = relationship("User", back_populates="organization",
                            foreign_keys="User.organization_id")


# ── MFA / 2FA ─────────────────────────────────────────────────────────────────

class MFAConfig(Base):
    """TOTP-based MFA configuration per user."""
    __tablename__ = "mfa_configs"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id      = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"),
                          nullable=False, unique=True, index=True)
    totp_secret  = Column(String(512), nullable=False)  # Fernet-encrypted base32 secret (v2:<salt>.<token>)
    is_enabled   = Column(Boolean, default=False)       # False until first verification
    verified_at  = Column(DateTime(timezone=True), nullable=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

    user         = relationship("User", foreign_keys=[user_id])
    backup_codes = relationship("MFABackupCode", back_populates="mfa_config",
                                cascade="all, delete-orphan")


class MFABackupCode(Base):
    """One-time backup codes (8 per user, each usable once)."""
    __tablename__ = "mfa_backup_codes"

    id         = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    mfa_id     = Column(String(36), ForeignKey("mfa_configs.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    code_hash  = Column(String(128), nullable=False)    # bcrypt hash of 8-char code
    used_at    = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    mfa_config = relationship("MFAConfig", back_populates="backup_codes")


class WebAuthnCredential(Base):
    """Registered passkey / FIDO2 credential for a user."""
    __tablename__ = "webauthn_credentials"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    credential_id = Column(String(255), nullable=False, unique=True, index=True)
    public_key = Column(Text, nullable=False)  # base64url encoded COSE public key bytes
    sign_count = Column(Integer, nullable=False, default=0)
    transports = Column(Text, nullable=True)  # JSON list
    name = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", foreign_keys=[user_id])


class MFAChallenge(Base):
    """One-time MFA login challenge used to prevent replay of short-lived JWTs."""
    __tablename__ = "mfa_challenges"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_jti = Column(String(36), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    consumed_at = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", foreign_keys=[user_id])


# ── Slack / Teams ─────────────────────────────────────────────────────────────

class SlackConfig(Base):
    """Slack or Microsoft Teams workspace integration."""
    __tablename__ = "slack_configs"

    id            = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    platform      = Column(String(10), default="slack")  # slack | teams
    workspace_name = Column(String(255), nullable=True)
    bot_token     = Column(Text, nullable=True)          # xoxb-... (stored encrypted)
    webhook_url   = Column(Text, nullable=True)          # incoming webhook fallback
    default_channel = Column(String(100), nullable=True) # #contecflow-alerts
    is_active     = Column(Boolean, default=True)
    # Event subscriptions (JSON list of enabled events)
    subscriptions = Column(Text, default='["task_overdue","budget_alert","ticket_sla"]')
    # Slash command token for verification
    slash_token   = Column(String(255), nullable=True)
    last_ping_at  = Column(DateTime(timezone=True), nullable=True)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())

    notifications = relationship("SlackNotificationLog", back_populates="config",
                                 cascade="all, delete-orphan")


class SlackNotificationLog(Base):
    """Audit log of every Slack/Teams message sent."""
    __tablename__ = "slack_notification_logs"

    id         = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    config_id  = Column(String(36), ForeignKey("slack_configs.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    channel    = Column(String(100), nullable=True)
    event_type = Column(String(50), nullable=True)   # task_overdue | budget_alert | ...
    message    = Column(Text, nullable=True)
    status     = Column(String(20), default="sent")  # sent | failed
    error      = Column(String(500), nullable=True)
    sent_at    = Column(DateTime(timezone=True), server_default=func.now())
    source_id  = Column(String(36), nullable=True)   # task/ticket/project id

    config = relationship("SlackConfig", back_populates="notifications")


# ── Multi-period Budgets ──────────────────────────────────────────────────────

class Budget(Base):
    """Annual budget for a department or cost centre."""
    __tablename__ = "budgets"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name        = Column(String(255), nullable=False)
    year        = Column(Integer, nullable=False, index=True)
    department  = Column(String(100), nullable=True)
    project_id  = Column(String(36), ForeignKey("projects.id"), nullable=True)
    total_amount = Column(Float, nullable=False, default=0)
    currency    = Column(String(3), default=settings.DEFAULT_CURRENCY)
    notes       = Column(Text, nullable=True)
    is_approved = Column(Boolean, default=False)
    approved_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    created_by  = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())

    entries    = relationship("BudgetEntry", back_populates="budget",
                              cascade="all, delete-orphan",
                              order_by="BudgetEntry.month")
    approver   = relationship("User", foreign_keys=[approved_by])
    creator    = relationship("User", foreign_keys=[created_by])
    project    = relationship("Project")


class BudgetEntry(Base):
    """Monthly planned vs actual for a budget."""
    __tablename__ = "budget_entries"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    budget_id   = Column(String(36), ForeignKey("budgets.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    month       = Column(Integer, nullable=False)   # 1-12
    planned     = Column(Float, default=0)
    actual      = Column(Float, default=0)
    committed   = Column(Float, default=0)          # approved but not yet spent
    notes       = Column(Text, nullable=True)
    is_locked   = Column(Boolean, default=False)
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())

    budget = relationship("Budget", back_populates="entries")


# ── AI Task Estimation ────────────────────────────────────────────────────────

class AITaskEstimate(Base):
    """AI-generated hour estimate for a task, based on historical similar tasks."""
    __tablename__ = "ai_task_estimates"

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id         = Column(String(36), ForeignKey("tasks.id", ondelete="CASCADE"),
                             nullable=False, index=True)
    estimated_hours = Column(Float, nullable=False)
    confidence_pct  = Column(Float, default=0)      # 0-100
    similar_tasks   = Column(Text, nullable=True)   # JSON: list of similar task ids
    reasoning       = Column(Text, nullable=True)   # AI explanation
    model_used      = Column(String(50), default="rule_based")
    accepted        = Column(Boolean, nullable=True) # PM accepted/rejected
    accepted_at     = Column(DateTime(timezone=True), nullable=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())

    task = relationship("Task")


# ── AI Ticket Triage ──────────────────────────────────────────────────────────

class AITicketTriage(Base):
    """AI-suggested triage for a service desk ticket."""
    __tablename__ = "ai_ticket_triages"

    id                   = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    ticket_id            = Column(String(36), ForeignKey("sd_tickets.id", ondelete="CASCADE"),
                                  nullable=False, index=True)
    suggested_category   = Column(String(100), nullable=True)
    suggested_priority   = Column(String(20), nullable=True)
    suggested_agent_id   = Column(String(36), ForeignKey("users.id"), nullable=True)
    suggested_kb_article = Column(String(36), nullable=True)
    confidence_pct       = Column(Float, default=0)
    reasoning            = Column(Text, nullable=True)
    accepted             = Column(Boolean, nullable=True)
    accepted_by          = Column(String(36), ForeignKey("users.id"), nullable=True)
    accepted_at          = Column(DateTime(timezone=True), nullable=True)
    created_at           = Column(DateTime(timezone=True), server_default=func.now())

    suggested_agent = relationship("User", foreign_keys=[suggested_agent_id])
    acceptor        = relationship("User", foreign_keys=[accepted_by])


# ── Scenario Planning / What-if ───────────────────────────────────────────────

class ScenarioModel(Base):
    """What-if capacity scenario — simulate impact of new projects."""
    __tablename__ = "scenario_models"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name        = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    base_date   = Column(Date, nullable=True)
    horizon_weeks = Column(Integer, default=12)
    status      = Column(String(20), default="draft")  # draft | computed | archived
    created_by  = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    computed_at = Column(DateTime(timezone=True), nullable=True)
    # Computed results stored as JSON
    results     = Column(Text, nullable=True)   # JSON: capacity gaps, overload weeks

    creator  = relationship("User", foreign_keys=[created_by])
    projects = relationship("ScenarioProject", back_populates="scenario",
                            cascade="all, delete-orphan")


class ScenarioProject(Base):
    """Simulated project inside a what-if scenario."""
    __tablename__ = "scenario_projects"

    id            = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scenario_id   = Column(String(36), ForeignKey("scenario_models.id", ondelete="CASCADE"),
                           nullable=False, index=True)
    # Either link to existing project OR define a hypothetical one
    project_id    = Column(String(36), ForeignKey("projects.id"), nullable=True)
    name          = Column(String(255), nullable=False)
    start_date    = Column(Date, nullable=True)
    end_date      = Column(Date, nullable=True)
    total_hours   = Column(Float, default=0)
    # Required skill breakdown (JSON: {skill_name: hours})
    skill_demand  = Column(Text, nullable=True)
    is_existing   = Column(Boolean, default=False)  # True = real project, False = hypothetical

    scenario = relationship("ScenarioModel", back_populates="projects")
    project  = relationship("Project")


# ── PDF Export Jobs ───────────────────────────────────────────────────────────

class PDFExportJob(Base):
    """Queued/completed PDF export request."""
    __tablename__ = "pdf_export_jobs"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    export_type = Column(String(50), nullable=False)  # report | invoice | project_summary
    source_id   = Column(String(36), nullable=True)   # report_id / invoice_id / project_id
    status      = Column(String(20), default="queued")  # queued | generating | ready | failed
    file_path   = Column(String(500), nullable=True)  # server path when ready
    file_size   = Column(Integer, nullable=True)
    params      = Column(Text, nullable=True)         # JSON: filters, date range, etc.
    error       = Column(String(500), nullable=True)
    requested_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    requester = relationship("User", foreign_keys=[requested_by])


# ── BI Connector Tokens ───────────────────────────────────────────────────────

class BIToken(Base):
    """Access token for BI tools (Power BI, Tableau, Metabase)."""
    __tablename__ = "bi_tokens"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name        = Column(String(255), nullable=False)
    tool        = Column(String(30), default="powerbi")  # powerbi | tableau | metabase | generic
    token_hash  = Column(String(128), nullable=False)    # bcrypt
    token_prefix = Column(String(16), nullable=True)     # bi_xxxxx
    scopes      = Column(Text, default='["read"]')       # JSON
    is_active   = Column(Boolean, default=True)
    expires_at  = Column(DateTime(timezone=True), nullable=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    requests_today = Column(Integer, default=0)
    created_by  = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())

    creator = relationship("User", foreign_keys=[created_by])
