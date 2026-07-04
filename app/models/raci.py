"""
v25 Models — Market-leader feature set expansion:
  1. RACI Matrix       — Responsibility matrix per project (R/A/C/I per item × user)
  2. Sprint Retro Notes — Saved retrospective notes per sprint
  3. Burnout Risk Log  — Weekly burnout risk snapshots per user
  4. Project Changelog  — Structured release entries generated from tasks/milestones
"""
from sqlalchemy import Column, String, DateTime, Date, Text, Float, Boolean, Integer, ForeignKey, Enum
from sqlalchemy.orm import relationship
from app.core.timeutil import utcnow
import enum
from uuid import uuid4

from app.db.base import Base


# ─────────────────────────────────────────────────────────────────────────────
# 1. RACI Matrix
# ─────────────────────────────────────────────────────────────────────────────

class RACIRole(str, enum.Enum):
    responsible  = "R"   # Does the work
    accountable  = "A"   # Ultimately answerable
    consulted    = "C"   # Provides input
    informed     = "I"   # Kept in the loop


class RACIEntry(Base):
    """
    One cell in a RACI matrix: (project, item) × (user, role).
    item_type: 'deliverable' | 'milestone' | 'phase' | 'custom'
    """
    __tablename__ = "raci_entries"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    project_id  = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    item_type   = Column(String(32),  nullable=False)          # deliverable / milestone / phase / custom
    item_label  = Column(String(200), nullable=False)          # Display label for the row
    item_id     = Column(String(36),  nullable=True)           # Optional FK to the source entity
    user_id     = Column(String(36),  ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role        = Column(Enum(RACIRole), nullable=False)

    created_at  = Column(DateTime, default=utcnow)
    updated_at  = Column(DateTime, default=utcnow, onupdate=utcnow)
    is_active   = Column(Boolean, default=True, nullable=False, server_default="1", index=True)  # audit #36 soft-delete

    user    = relationship("User", lazy="joined")
    project = relationship("Project")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Sprint Retrospective Notes
# ─────────────────────────────────────────────────────────────────────────────

class SprintRetroNote(Base):
    """
    Saved retrospective analysis for a closed sprint.
    Stores both the AI-computed insights and any manual notes.
    """
    __tablename__ = "sprint_retro_notes"

    id         = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    sprint_id  = Column(String(36), ForeignKey("sprints.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)

    # Computed metrics snapshot
    velocity_completed  = Column(Float, nullable=True)   # story points / hours completed
    velocity_planned    = Column(Float, nullable=True)
    completion_rate_pct = Column(Float, nullable=True)
    blocked_count       = Column(Integer, nullable=True)
    added_mid_sprint    = Column(Integer, nullable=True)  # scope creep count
    carryover_count     = Column(Integer, nullable=True)

    # Structured insights (computed)
    went_well_items    = Column(Text, nullable=True)   # JSON list of strings
    improve_items      = Column(Text, nullable=True)   # JSON list of strings
    action_items       = Column(Text, nullable=True)   # JSON list of {text, owner_id}
    risk_flags         = Column(Text, nullable=True)   # JSON list of warning strings

    # Manual override / additions
    manual_notes       = Column(Text, nullable=True)
    facilitated_by_id  = Column(String(36), ForeignKey("users.id"), nullable=True)

    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
    is_active  = Column(Boolean, default=True, nullable=False, server_default="1", index=True)  # audit #36 soft-delete

    sprint         = relationship("Sprint")
    facilitated_by = relationship("User", foreign_keys=[facilitated_by_id])


# ─────────────────────────────────────────────────────────────────────────────
# 3. Burnout Risk Snapshot
# ─────────────────────────────────────────────────────────────────────────────

class BurnoutRiskLevel(str, enum.Enum):
    green  = "green"   # Healthy load
    yellow = "yellow"  # Approaching overload
    orange = "orange"  # Sustained overload
    red    = "red"     # Burnout risk — intervention needed


class BurnoutRiskSnapshot(Base):
    """
    Weekly burnout-risk snapshot per user.
    Computed from: consecutive overload weeks, load %, unplanned hours, after-hours patterns.
    """
    __tablename__ = "burnout_risk_snapshots"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    user_id     = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    week_start  = Column(Date, nullable=False)

    load_pct              = Column(Float, nullable=True)   # actual / capacity * 100
    overload_weeks_streak = Column(Integer, default=0)     # consecutive weeks >100%
    avg_load_4w           = Column(Float, nullable=True)   # rolling 4-week average
    risk_level            = Column(Enum(BurnoutRiskLevel), default=BurnoutRiskLevel.green)
    risk_score            = Column(Float, default=0.0)     # 0-100 composite score
    factors               = Column(Text, nullable=True)    # JSON list of contributing factors

    created_at = Column(DateTime, default=utcnow)

    user = relationship("User", lazy="joined")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Project Changelog entries
# ─────────────────────────────────────────────────────────────────────────────

class ChangelogEntryType(str, enum.Enum):
    feature    = "feature"
    bugfix     = "bugfix"
    improvement = "improvement"
    milestone  = "milestone"
    breaking   = "breaking"


class ProjectChangelogEntry(Base):
    """
    Structured release/changelog entry for a project.
    Can be generated automatically from completed tasks or created manually.
    """
    __tablename__ = "project_changelog_entries"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    project_id  = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    version_tag = Column(String(50),  nullable=True)      # e.g. "v2.3.0", "Sprint 14"
    entry_date  = Column(Date, nullable=False)
    entry_type  = Column(Enum(ChangelogEntryType), default=ChangelogEntryType.feature)
    title       = Column(String(300), nullable=False)
    description = Column(Text,        nullable=True)
    is_auto_generated = Column(Boolean, default=False)    # True = came from task aggregation
    source_task_ids   = Column(Text,  nullable=True)      # JSON list of task IDs that generated this

    author_id  = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
    is_active  = Column(Boolean, default=True, nullable=False, server_default="1", index=True)  # audit #36 soft-delete

    author  = relationship("User", foreign_keys=[author_id])
    project = relationship("Project")


# ─────────────────────────────────────────────────────────────────────────────
# 5. UAT Cases
# ─────────────────────────────────────────────────────────────────────────────

class UATStatus(str, enum.Enum):
    pending  = "pending"   # Not yet executed
    passed   = "passed"    # Test passed by client/tester
    failed   = "failed"    # Test failed — needs fix
    blocked  = "blocked"   # Blocked, can't execute
    skipped  = "skipped"   # Intentionally skipped


class UATCase(Base):
    """
    UAT (User Acceptance Test) case linked to a project and optionally a task.
    Defines the acceptance criterion and records its execution result.
    """
    __tablename__ = "uat_cases"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    project_id  = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    task_id     = Column(String(36), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True)

    title           = Column(String(300), nullable=False)
    description     = Column(Text,        nullable=True)   # Steps to execute
    expected_result = Column(Text,        nullable=True)   # What "passing" looks like
    actual_result   = Column(Text,        nullable=True)   # Filled in when test is run
    status          = Column(Enum(UATStatus), default=UATStatus.pending)
    priority        = Column(String(20),  default="medium")  # low | medium | high | critical

    assigned_to_id  = Column(String(36), ForeignKey("users.id"), nullable=True)
    notes           = Column(Text, nullable=True)

    executed_at = Column(DateTime, nullable=True)
    created_at  = Column(DateTime, default=utcnow)
    updated_at  = Column(DateTime, default=utcnow, onupdate=utcnow)
    is_active   = Column(Boolean, default=True, nullable=False, server_default="1", index=True)  # audit #36 soft-delete

    project     = relationship("Project")
    task        = relationship("Task", foreign_keys=[task_id])
    assigned_to = relationship("User", foreign_keys=[assigned_to_id])
