"""Módulo de evaluaciones de rendimiento 360°."""
import uuid
import enum
from sqlalchemy import Column, String, Text, Float, Boolean, ForeignKey, Date
from sqlalchemy import DateTime, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base


class ReviewCycleStatus(str, enum.Enum):
    draft     = "draft"
    active    = "active"
    closed    = "closed"


class ReviewStatus(str, enum.Enum):
    pending   = "pending"
    submitted = "submitted"
    approved  = "approved"


class ReviewCycle(Base):
    """Ciclo de evaluación (trimestral, anual…)."""
    __tablename__ = "review_cycles"
    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name        = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    start_date  = Column(Date, nullable=True)
    end_date    = Column(Date, nullable=True)
    status      = Column(Enum(ReviewCycleStatus), default=ReviewCycleStatus.draft)
    include_self   = Column(Boolean, default=True)
    include_peers  = Column(Boolean, default=True)
    include_manager = Column(Boolean, default=True)
    created_by  = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    reviews     = relationship("PerformanceReview", back_populates="cycle",
                               cascade="all, delete-orphan")


class PerformanceReview(Base):
    """Evaluación individual dentro de un ciclo."""
    __tablename__ = "performance_reviews"
    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    cycle_id     = Column(String(36), ForeignKey("review_cycles.id", ondelete="CASCADE"),
                          nullable=False, index=True)
    reviewee_id  = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    reviewer_id  = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    review_type  = Column(String(20), default="self")  # self | peer | manager | upward
    status       = Column(Enum(ReviewStatus), default=ReviewStatus.pending)
    # Puntuaciones 1-5
    score_quality    = Column(Float, nullable=True)
    score_delivery   = Column(Float, nullable=True)
    score_teamwork   = Column(Float, nullable=True)
    score_leadership = Column(Float, nullable=True)
    score_innovation = Column(Float, nullable=True)
    score_overall    = Column(Float, nullable=True)
    # Texto libre
    strengths    = Column(Text, nullable=True)
    improvements = Column(Text, nullable=True)
    goals_next   = Column(Text, nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
    cycle        = relationship("ReviewCycle", back_populates="reviews")
    reviewee     = relationship("User", foreign_keys=[reviewee_id])
    reviewer     = relationship("User", foreign_keys=[reviewer_id])
