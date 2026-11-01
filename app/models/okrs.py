"""Módulo OKRs — Objectives and Key Results."""
import uuid
import enum
from sqlalchemy import Column, String, Text, Float, Integer, ForeignKey, Date, Boolean
from sqlalchemy import DateTime, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base


class OKRStatus(str, enum.Enum):
    draft      = "draft"
    active     = "active"
    completed  = "completed"
    cancelled  = "cancelled"


class OKRPeriod(str, enum.Enum):
    q1 = "Q1"; q2 = "Q2"; q3 = "Q3"; q4 = "Q4"
    h1 = "H1"; h2 = "H2"
    annual = "annual"


class Objective(Base):
    """Objetivo de alto nivel."""
    __tablename__ = "okr_objectives"
    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    title       = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    owner_id    = Column(String(36), ForeignKey("users.id"), nullable=True)
    team_id     = Column(String(36), nullable=True)          # departamento libre
    project_id  = Column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    period      = Column(Enum(OKRPeriod), default=OKRPeriod.q1)
    year        = Column(Integer, nullable=False, default=lambda: __import__('datetime').datetime.now().year)
    status      = Column(Enum(OKRStatus), default=OKRStatus.draft)
    progress    = Column(Float, default=0.0)   # 0-100, calculado de KRs
    is_active   = Column(Boolean, default=True, nullable=False)  # Soft delete
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())
    owner       = relationship("User", foreign_keys=[owner_id])
    key_results = relationship("KeyResult", back_populates="objective",
                               cascade="all, delete-orphan", order_by="KeyResult.title")

    def __repr__(self) -> str:
        return f"<Objective id={self.id!r} title={self.title!r}>"


class KRType(str, enum.Enum):
    percentage = "percentage"   # 0-100%
    number     = "number"       # valor numérico libre
    boolean    = "boolean"      # hecho/no hecho
    currency   = "currency"     # importe €


class KeyResult(Base):
    """Resultado clave medible asociado a un Objective."""
    __tablename__ = "okr_key_results"
    id            = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    objective_id  = Column(String(36), ForeignKey("okr_objectives.id", ondelete="CASCADE"),
                           nullable=False, index=True)
    title         = Column(String(500), nullable=False)
    kr_type       = Column(Enum(KRType), default=KRType.percentage)
    target_value  = Column(Float, nullable=True, default=100)
    current_value = Column(Float, nullable=True, default=0)
    unit          = Column(String(50), nullable=True)        # %, €, usuarios, NPS…
    owner_id      = Column(String(36), ForeignKey("users.id"), nullable=True)
    due_date      = Column(Date, nullable=True)
    progress      = Column(Float, default=0.0)   # 0-100
    notes         = Column(Text, nullable=True)
    is_active     = Column(Boolean, default=True, nullable=False)  # Soft delete
    created_at    = Column(DateTime(timezone=True), server_default=func.now())
    updated_at    = Column(DateTime(timezone=True), onupdate=func.now())
    objective     = relationship("Objective", back_populates="key_results")
    owner         = relationship("User", foreign_keys=[owner_id])
    checkins      = relationship("KRCheckin", back_populates="kr",
                                 cascade="all, delete-orphan",
                                 order_by="KRCheckin.created_at.desc()")

    def __repr__(self) -> str:
        return f"<KeyResult id={self.id!r} title={self.title!r}>"


class KRCheckin(Base):
    """Actualización de progreso de un Key Result."""
    __tablename__ = "okr_checkins"
    id         = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    kr_id      = Column(String(36), ForeignKey("okr_key_results.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    value      = Column(Float, nullable=False)
    note       = Column(String(500), nullable=True)
    author_id  = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    kr         = relationship("KeyResult", back_populates="checkins")
    author     = relationship("User", foreign_keys=[author_id])

    def __repr__(self) -> str:
        return f"<KRCheckin id={self.id!r} value={self.value!r}>"
