"""
v24 — New market-leader features:
  - ActivityEvent   : Unified activity feed per entity
  - Mention         : @mention linking comment → user + notification
  - ProjectHealthSnapshot : Auto-computed health score per project
  - RecurringTask   : Recurring task definition (rrule-style)
  - ResourceDemandForecast: Pipeline-linked resource demand
  - VendorScore     : Vendor scorecard per evaluation period
"""
import uuid
import enum
from sqlalchemy import (
    Column, String, Float, Integer, Boolean,
    Date, DateTime, Text, ForeignKey, Enum
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base


# ── Activity Feed ─────────────────────────────────────────────────────────────

class ActivityEvent(Base):
    """
    Append-only log of every meaningful action across the app.
    Powers the per-project / per-task / per-ticket activity feed.
    """
    __tablename__ = "activity_events"

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    # Tenant isolation — must be set on every INSERT so TenantSession can scope reads.
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"),
                             nullable=True, index=True)
    entity_type     = Column(String(50), nullable=False, index=True)  # project task ticket sprint
    entity_id       = Column(String(36), nullable=False, index=True)
    entity_code     = Column(String(50), nullable=True)               # TSK-042, PRJ-007 ...
    actor_id        = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    actor_name      = Column(String(255), nullable=True)              # snapshot for delete safety
    verb          = Column(String(80), nullable=False)              # created, closed, commented, mentioned, status_changed ...
    detail        = Column(Text, nullable=True)                     # JSON or plain text detail
    target_type   = Column(String(50), nullable=True)               # e.g. "user" if verb=assigned_to
    target_id     = Column(String(36), nullable=True)
    target_name   = Column(String(255), nullable=True)
    created_at    = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    actor = relationship("User", foreign_keys=[actor_id])


# ── Project Health Score ──────────────────────────────────────────────────────

class ProjectHealthSnapshot(Base):
    """
    Periodic snapshot of composite project health (0-100).
    Components: schedule, budget, quality, team, client.
    """
    __tablename__ = "project_health_snapshots"

    id               = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id       = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    score            = Column(Float, nullable=False)          # 0-100 composite
    schedule_score   = Column(Float, nullable=True)           # % tasks on time
    budget_score     = Column(Float, nullable=True)           # burn rate vs. budget
    quality_score    = Column(Float, nullable=True)           # open defects / open risks
    velocity_score   = Column(Float, nullable=True)           # sprint velocity trend
    client_score     = Column(Float, nullable=True)           # NPS / client satisfaction
    detail           = Column(Text, nullable=True)            # JSON breakdown
    snapshot_at      = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    project = relationship("Project")


# ── Recurring Tasks ───────────────────────────────────────────────────────────

class RecurringFreqType(str, enum.Enum):
    daily   = "daily"
    weekly  = "weekly"
    monthly = "monthly"
    custom  = "custom"   # explicit interval_days


class RecurringTask(Base):
    """
    Template for tasks that repeat on a schedule.
    The materializer endpoint creates concrete Task records.
    """
    __tablename__ = "recurring_tasks"

    id               = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id       = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    title            = Column(String(500), nullable=False)
    description      = Column(Text, nullable=True)
    priority         = Column(String(20), default="medium")
    assignee_id      = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    estimated_hours  = Column(Float, nullable=True)
    story_points     = Column(Integer, nullable=True)

    freq             = Column(Enum(RecurringFreqType), default=RecurringFreqType.weekly, nullable=False)
    interval_days    = Column(Integer, default=7)              # used when freq=custom
    weekday_mask     = Column(Integer, nullable=True)          # bitmask Mon=1 ... Sun=64
    start_date       = Column(Date, nullable=False)
    end_date         = Column(Date, nullable=True)             # null = runs forever
    due_offset_days  = Column(Integer, default=0)              # task.due_date = occurrence_date + offset

    last_generated   = Column(Date, nullable=True)             # last date a task was created
    is_active        = Column(Boolean, default=True)
    created_by       = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at       = Column(DateTime(timezone=True), server_default=func.now())

    project  = relationship("Project")
    assignee = relationship("User", foreign_keys=[assignee_id])
    creator  = relationship("User", foreign_keys=[created_by])


# ── Resource Demand Forecast (from pipeline) ──────────────────────────────────

class ResourceDemandForecast(Base):
    """
    Weighted resource demand derived from open opportunities in the pipeline.
    One row per opportunity × skill/role requirement.
    """
    __tablename__ = "resource_demand_forecasts"

    id               = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    opportunity_id   = Column(String(36), ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False, index=True)
    role_or_skill    = Column(String(100), nullable=False)      # e.g. "Backend Developer", "DevOps"
    hours_required   = Column(Float, nullable=False)
    weighted_hours   = Column(Float, nullable=True)             # hours × probability/100
    start_date       = Column(Date, nullable=True)
    end_date         = Column(Date, nullable=True)
    notes            = Column(String(500), nullable=True)
    created_at       = Column(DateTime(timezone=True), server_default=func.now())
    updated_at       = Column(DateTime(timezone=True), onupdate=func.now())

    opportunity = relationship("Opportunity")


# ── Vendor Scorecard ──────────────────────────────────────────────────────────

class VendorScore(Base):
    """
    Periodic vendor performance evaluation (quarterly, annually, ad-hoc).
    Scores 0-10 for each dimension; composite score is weighted average.
    """
    __tablename__ = "vendor_scores"

    id               = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    vendor_id        = Column(String(36), ForeignKey("alm_vendors.id", ondelete="CASCADE"), nullable=False, index=True)
    period           = Column(String(20), nullable=False)       # e.g. "Q1-2026", "2026"
    evaluator_id     = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Dimension scores (0-10)
    sla_score        = Column(Float, nullable=True)             # meets contracted SLAs
    quality_score    = Column(Float, nullable=True)             # delivery / product quality
    support_score    = Column(Float, nullable=True)             # responsiveness, resolution
    price_score      = Column(Float, nullable=True)             # value for money
    innovation_score = Column(Float, nullable=True)             # roadmap, new features
    compliance_score = Column(Float, nullable=True)             # regulatory, certifications

    composite_score  = Column(Float, nullable=True)             # auto-computed weighted avg
    incidents_count  = Column(Integer, default=0)               # number of incidents in period
    notes            = Column(Text, nullable=True)
    evaluated_at     = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    vendor    = relationship("ALMVendor")
    evaluator = relationship("User", foreign_keys=[evaluator_id])
