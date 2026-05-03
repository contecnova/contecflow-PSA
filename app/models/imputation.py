from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Text, Date, Boolean, Integer, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.db.base import Base


class Imputation(Base):
    """
    Core table: each row = one person, one task, one day, N hours.
    This drives ALL cost and productivity calculations.
    """
    __tablename__ = "imputations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Who
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # What and where
    task_id = Column(String(36), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)

    # When
    date = Column(Date, nullable=False, index=True)

    # How much
    hours = Column(Float, nullable=False)

    # Cost snapshot at time of imputation (denormalized for historical accuracy)
    hourly_rate_snapshot = Column(Float, nullable=True)  # Rate at time of log
    cost_amount = Column(Float, nullable=True)            # hours × rate

    # Context
    description = Column(Text, nullable=True)

    # Approval workflow (optional)
    is_approved = Column(Boolean, default=False)
    approved_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)

    # Billable flag
    is_billable = Column(Boolean, default=False)

    # Invoicing: set to True once this imputation is included in a persisted Invoice
    is_invoiced = Column(Boolean, default=False, nullable=False)
    invoiced_invoice_id = Column(String(36), nullable=True, index=True)  # no FK — avoids circular dep

    # Jira worklog sync
    jira_worklog_id = Column(String(50), nullable=True)

    # Timer session that generated this imputation (if any)
    timer_session_id = Column(String(36), nullable=True, index=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="imputations", foreign_keys=[user_id])
    task = relationship("Task", back_populates="imputations")
    project = relationship("Project", back_populates="imputations")
    approver = relationship("User", foreign_keys=[approved_by])

    def __repr__(self):
        return f"<Imputation user={self.user_id} task={self.task_id} date={self.date} hours={self.hours}>"


# ── Timer Sessions ─────────────────────────────────────────────────────────

class TimerSession(Base):
    """Active timer for time tracking."""
    __tablename__ = "timer_sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Who and what
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    task_id = Column(String(36), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)

    # Timer state
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    paused_at = Column(DateTime(timezone=True), nullable=True)
    paused_duration_secs = Column(Integer, default=0)  # Total pause time in seconds
    ended_at = Column(DateTime(timezone=True), nullable=True)

    # Associated imputation (once stopped)
    imputation_id = Column(String(36), ForeignKey("imputations.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    task = relationship("Task", foreign_keys=[task_id])
    project = relationship("Project", foreign_keys=[project_id])
    imputation = relationship("Imputation", foreign_keys=[imputation_id])

    __table_args__ = (
        # Index for efficient lookup of active timer (where ended_at IS NULL)
        Index('ix_timer_session_user_active', 'user_id', 'ended_at'),
    )


# ── Imputation Alerts ──────────────────────────────────────────────────────

class ImputationAlert(Base):
    """Alerts for missing/incomplete imputations."""
    __tablename__ = "imputation_alerts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Alert date (which day was not fully imputed)
    alert_date = Column(Date, nullable=False, index=True)
    alert_type = Column(String(50), default="missing_hours")  # missing_hours | incomplete_day

    # Lifecycle
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    dismissed_at = Column(DateTime(timezone=True), nullable=True)  # When user dismisses/snoozes

    # Relationships
    user = relationship("User", foreign_keys=[user_id])


# ── Imputation Snapshots ───────────────────────────────────────────────────

class ImputationSnapshot(Base):
    """Daily snapshot of total hours logged."""
    __tablename__ = "imputation_snapshots"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Date this snapshot represents
    snapshot_date = Column(Date, nullable=False, index=True)

    # Hours logged (calculated from imputations)
    total_hours = Column(Float, default=0.0)
    billable_hours = Column(Float, default=0.0)
    approved_hours = Column(Float, default=0.0)

    # Flag if complete (i.e., expected hours are logged)
    is_complete = Column(Boolean, default=False)

    # When this snapshot was taken
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        Index('ix_imputation_snapshot_user_date', 'user_id', 'snapshot_date'),
    )
