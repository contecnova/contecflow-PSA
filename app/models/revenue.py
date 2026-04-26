"""
revenue.py — ASC 606 / IFRS 15 Revenue Recognition models.

Tables:
  rev_contracts      — contrato de reconocimiento ligado a un proyecto
  rev_obligations    — obligaciones de desempeño (performance obligations)
  rev_period_closes  — cierre contable mensual (inmutable una vez cerrado)
  rev_entries        — entradas contables de reconocimiento (inmutables)
"""
import enum
import uuid

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Enum, Float,
    ForeignKey, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class ASCMethod(str, enum.Enum):
    over_time    = "over_time"       # T&M — proporcional a horas/coste
    milestone    = "milestone"       # Precio fijo — al completar hito
    consumption  = "consumption"     # Bolsa de horas — al consumir
    straight_line = "straight_line"  # Retainer — 1/N por mes


class EntryType(str, enum.Enum):
    recognized = "recognized"
    deferred   = "deferred"
    unbilled   = "unbilled"
    reversal   = "reversal"


# ── RevenueContract ────────────────────────────────────────────────────────────

class RevenueContract(Base):
    """Contrato ASC 606 ligado a un proyecto."""
    __tablename__ = "rev_contracts"

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id      = Column(String(36), ForeignKey("projects.id",      ondelete="CASCADE"), nullable=False, index=True)
    client_id       = Column(String(36), ForeignKey("clients.id",       ondelete="SET NULL"), nullable=True)

    name            = Column(String(255), nullable=False)
    contract_value  = Column(Float, nullable=False, default=0.0)
    currency        = Column(String(8), nullable=False, default="EUR")
    method          = Column(Enum(ASCMethod), nullable=False, default=ASCMethod.over_time)

    start_date      = Column(Date, nullable=True)
    end_date        = Column(Date, nullable=True)
    # straight_line: número de meses de duración
    duration_months = Column(Integer, nullable=True)

    is_active       = Column(Boolean, nullable=False, default=True)
    notes           = Column(Text, nullable=True)

    created_at      = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at      = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    obligations = relationship("RevenueObligation", back_populates="contract", cascade="all, delete-orphan")
    entries     = relationship("RevenueEntry",      back_populates="contract")


# ── RevenueObligation ──────────────────────────────────────────────────────────

class RevenueObligation(Base):
    """Obligación de desempeño dentro de un contrato ASC 606."""
    __tablename__ = "rev_obligations"

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    contract_id     = Column(String(36), ForeignKey("rev_contracts.id", ondelete="CASCADE"), nullable=False, index=True)
    # Vínculo opcional a un milestone específico (método milestone)
    milestone_id    = Column(String(36), ForeignKey("milestones.id",    ondelete="SET NULL"), nullable=True)

    name            = Column(String(255), nullable=False)
    # % del valor total del contrato asignado a esta obligación (0–100)
    allocated_pct   = Column(Float, nullable=False, default=100.0)
    allocated_amount = Column(Float, nullable=False, default=0.0)

    is_satisfied    = Column(Boolean, nullable=False, default=False)
    satisfied_date  = Column(Date, nullable=True)

    created_at      = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    contract = relationship("RevenueContract", back_populates="obligations")


# ── RevenuePeriodClose ─────────────────────────────────────────────────────────

class RevenuePeriodClose(Base):
    """Cierre contable mensual — bloquea las entradas del período."""
    __tablename__ = "rev_period_closes"
    __table_args__ = (
        UniqueConstraint("organization_id", "period_year", "period_month", name="uq_period_close"),
    )

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)

    period_year     = Column(Integer, nullable=False)
    period_month    = Column(Integer, nullable=False)  # 1–12

    closed_by       = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    closed_at       = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    notes           = Column(Text, nullable=True)

    entries = relationship("RevenueEntry", back_populates="period_close")


# ── RevenueEntry ───────────────────────────────────────────────────────────────

class RevenueEntry(Base):
    """
    Entrada contable de reconocimiento de ingresos.
    Inmutable — nunca se elimina; las correcciones crean una entrada de tipo 'reversal'.
    """
    __tablename__ = "rev_entries"

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    rev_contract_id = Column(String(36), ForeignKey("rev_contracts.id", ondelete="RESTRICT"), nullable=False, index=True)
    period_close_id = Column(String(36), ForeignKey("rev_period_closes.id", ondelete="SET NULL"), nullable=True)

    # Origen de la entrada
    milestone_id    = Column(String(36), ForeignKey("milestones.id",   ondelete="SET NULL"), nullable=True)
    timesheet_id    = Column(String(36), nullable=True)  # referencia libre a hoja de horas

    entry_type      = Column(Enum(EntryType), nullable=False, default=EntryType.recognized)
    amount          = Column(Float, nullable=False, default=0.0)
    currency        = Column(String(8), nullable=False, default="EUR")

    period_year     = Column(Integer, nullable=False)
    period_month    = Column(Integer, nullable=False)

    # Referencia a la entrada que revierte (si es reversal)
    reverses_entry_id = Column(String(36), ForeignKey("rev_entries.id", ondelete="SET NULL"), nullable=True)

    description     = Column(Text, nullable=True)
    created_by      = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    contract     = relationship("RevenueContract",    back_populates="entries")
    period_close = relationship("RevenuePeriodClose", back_populates="entries")
