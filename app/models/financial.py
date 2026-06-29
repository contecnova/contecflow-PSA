from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Text, Date, Boolean, Integer, Enum
from app.models.money import Money
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
import uuid
from app.db.base import Base


class TimesheetStatus(str, enum.Enum):
    draft = "draft"           # Employee filling in
    submitted = "submitted"   # Sent for approval
    approved = "approved"     # PM approved
    rejected = "rejected"     # PM rejected, needs corrections


class Timesheet(Base):
    """Weekly timesheet - groups all imputations for a user/week."""
    __tablename__ = "timesheets"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    is_active = Column(Boolean, default=True, nullable=False, server_default="1", index=True)  # audit #36 soft-delete
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    week_start = Column(Date, nullable=False, index=True)  # Monday of the week
    week_end = Column(Date, nullable=False)

    status = Column(Enum(TimesheetStatus), default=TimesheetStatus.draft, nullable=False, index=True)

    total_hours = Column(Float, default=0)
    billable_hours = Column(Float, default=0)
    total_cost = Column(Money, default=0)

    # Approval
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_by = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    review_notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    reviewer = relationship("User", foreign_keys=[reviewed_by])


class CapacityPlan(Base):
    """Forward-looking capacity planning entries."""
    __tablename__ = "capacity_plans"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)

    week_start = Column(Date, nullable=False, index=True)
    planned_hours = Column(Float, nullable=False, default=0)
    is_active = Column(Boolean, default=True)
    notes = Column(String(255), nullable=True)

    created_by = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    project = relationship("Project", foreign_keys=[project_id])
    creator = relationship("User", foreign_keys=[created_by])


class ProjectMilestone(Base):
    """Project milestones linked to billing — SOW → Completion → Approval → Invoice flow."""
    __tablename__ = "project_milestones"

    id         = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)

    name        = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    is_active   = Column(Boolean, default=True)
    due_date    = Column(Date, nullable=True)
    sort_order  = Column(Integer, default=0)

    # ── Estado del flujo ────────────────────────────────────────────────────────
    # pending → completed → pending_approval → approved → invoiced
    billing_status  = Column(String(30), default="pending")
    is_completed    = Column(Boolean, default=False)
    completed_date  = Column(Date, nullable=True)
    completed_by    = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)

    # ── Aprobación ──────────────────────────────────────────────────────────────
    approval_requested_at  = Column(DateTime(timezone=True), nullable=True)
    approval_requested_by  = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    approved_at            = Column(DateTime(timezone=True), nullable=True)
    approved_by            = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    rejected_at            = Column(DateTime(timezone=True), nullable=True)
    rejected_by            = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    rejection_reason       = Column(Text, nullable=True)

    # ── Facturación ─────────────────────────────────────────────────────────────
    billing_amount  = Column(Money, nullable=True)    # € a facturar
    billing_pct     = Column(Float, nullable=True)    # % del contrato total (ratio)
    invoice_id      = Column(String(36), ForeignKey("invoices.id"), nullable=True, index=True)
    is_billed       = Column(Boolean, default=False)
    billed_at       = Column(Date, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    project             = relationship("Project")
    completer           = relationship("User", foreign_keys=[completed_by])
    approver            = relationship("User", foreign_keys=[approved_by])
    approval_requester  = relationship("User", foreign_keys=[approval_requested_by])
    rejector            = relationship("User", foreign_keys=[rejected_by])
    invoice             = relationship("Invoice", foreign_keys=[invoice_id])
