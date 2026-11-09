"""
Expense tracking — project-linked expense management with approval workflow.
"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Boolean, Enum, Date, Float, Integer, Index
from app.models.money import Money
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
    """Gasto del usuario imputado a un proyecto, con flujo de aprobación y reembolso."""
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
    amount      = Column(Money, nullable=False)
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
    # Revisión 2026-11: kilometraje (el importe lo calcula el servidor con
    # EXPENSE_MILEAGE_RATE) y los avisos de política vistos al enviar (JSON).
    km           = Column(Float, nullable=True)
    policy_flags = Column(Text, nullable=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
    updated_at   = Column(DateTime(timezone=True), onupdate=func.now())

    is_active    = Column(Boolean, default=True, nullable=False, server_default="1", index=True)  # audit #36 soft-delete

    user         = relationship("User", foreign_keys=[user_id])
    reviewer     = relationship("User", foreign_keys=[reviewed_by])
    project      = relationship("Project")
    contract     = relationship("Contract")

    def __repr__(self) -> str:
        return f"<Expense id={self.id!r} code={self.code!r}>"


# ── Revisión 2026-11: justificantes, reparto y políticas ─────────────────────

class ExpenseAttachment(Base):
    """Un justificante o documento del gasto (varios por gasto), en el almacén de ficheros."""
    __tablename__ = "expense_attachments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    expense_id = Column(String(36), ForeignKey("expenses.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    content_type = Column(String(120), nullable=True)
    size_bytes = Column(Integer, nullable=True)
    storage_key = Column(String(500), nullable=False)
    uploaded_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ExpenseAllocation(Base):
    """Reparto del gasto entre proyectos, en porcentaje (suman 100)."""
    __tablename__ = "expense_allocations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    expense_id = Column(String(36), ForeignKey("expenses.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    percentage = Column(Float, nullable=False)

    project = relationship("Project")


class ExpensePolicy(Base):
    """Una regla de gasto. Con acción `bloquear` el gasto no se puede enviar;
    con `avisar` se envía marcado, y un flujo de aprobación puede pedir un
    paso más para lo que excede una política (condición `policy_exceeded`)."""
    __tablename__ = "expense_policies"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    nombre = Column(String(200), nullable=False)
    categoria = Column(String(30), nullable=True)          # vacía: todas
    limite_por_gasto = Column(Float, nullable=True)
    limite_diario = Column(Float, nullable=True)            # por persona, día y categoría
    justificante_desde = Column(Float, nullable=True)       # importe desde el que hace falta adjuntar
    justificacion_desde = Column(Float, nullable=True)      # importe desde el que hace falta explicar (notas)
    accion = Column(String(10), nullable=False, default="bloquear")   # bloquear | avisar
    activa = Column(Boolean, nullable=False, default=True)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
