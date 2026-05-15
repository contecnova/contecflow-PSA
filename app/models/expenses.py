"""
Expense tracking — project-linked expense management with approval workflow.
"""
from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Text, Boolean, Enum, Date
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
import uuid
from app.db.base import Base
from app.core.config import settings


class ExpenseCategory(str, enum.Enum):
    travel       = "travel"
    accommodation = "accommodation"
    meals        = "meals"
    software     = "software"
    hardware     = "hardware"
    training     = "training"
    subcontract  = "subcontract"
    other        = "other"


class ExpenseStatus(str, enum.Enum):
    draft     = "draft"
    submitted = "submitted"
    approved  = "approved"
    rejected  = "rejected"
    reimbursed = "reimbursed"


class Expense(Base):
    __tablename__ = "expenses"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    code        = Column(String(20), nullable=False)       # EXP-0001

    # Who / What
    user_id     = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id  = Column(String(36), ForeignKey("projects.id"), nullable=True, index=True)
    contract_id = Column(String(36), ForeignKey("contracts.id"), nullable=True)

    # Expense details
    category    = Column(Enum(ExpenseCategory), nullable=False)
    description = Column(String(500), nullable=False)
    amount      = Column(Float, nullable=False)
    currency    = Column(String(3), default=settings.DEFAULT_CURRENCY)
    expense_date = Column(Date, nullable=False)
    is_billable = Column(Boolean, default=True)     # Charge to client?

    # Receipt
    receipt_url  = Column(String(500), nullable=True)
    receipt_name = Column(String(255), nullable=True)

    # Approval workflow
    status       = Column(Enum(ExpenseStatus), default=ExpenseStatus.draft, nullable=False, index=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_by  = Column(String(36), ForeignKey("users.id"), nullable=True)
    reviewed_at  = Column(DateTime(timezone=True), nullable=True)
    rejection_reason = Column(String(500), nullable=True)
    reimbursed_at = Column(DateTime(timezone=True), nullable=True)

    notes        = Column(Text, nullable=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
    updated_at   = Column(DateTime(timezone=True), onupdate=func.now())

    is_active    = Column(Boolean, default=True, nullable=False, server_default="1", index=True)  # audit #36 soft-delete

    user         = relationship("User", foreign_keys=[user_id])
    reviewer     = relationship("User", foreign_keys=[reviewed_by])
    project      = relationship("Project")
    contract     = relationship("Contract")
