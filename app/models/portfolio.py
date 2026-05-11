"""
Portfolio model — agrupa proyectos en carteras con seguimiento RAG y presupuesto consolidado.
"""
import enum
import uuid
from sqlalchemy import Column, String, Float, Text, Enum, ForeignKey, Date, DateTime, func, Boolean
from sqlalchemy.orm import relationship
from app.db.base import Base


class PortfolioStatus(str, enum.Enum):
    active   = "active"
    archived = "archived"
    planning = "planning"


class Portfolio(Base):
    __tablename__ = "portfolios"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name        = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status      = Column(Enum(PortfolioStatus), default=PortfolioStatus.active, nullable=False)
    is_active   = Column(Boolean, default=True)

    # Budget aggregation
    budget_total   = Column(Float, nullable=True)   # Total budget envelope (€)
    budget_spent   = Column(Float, nullable=True)   # Snapshot of spent (updated on demand)

    # Owner
    owner_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Dates
    start_date = Column(Date, nullable=True)
    end_date   = Column(Date, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    members  = relationship("PortfolioProject", back_populates="portfolio", cascade="all, delete-orphan")
    owner    = relationship("User", foreign_keys=[owner_id])


class PortfolioProject(Base):
    """Association table between Portfolio and Project."""
    __tablename__ = "portfolio_projects"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    portfolio_id = Column(String(36), ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id   = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)

    # Manual RAG override (when not auto-computed from EVM)
    rag_override   = Column(String(10), nullable=True)   # green | yellow | red
    is_active      = Column(Boolean, default=True)
    display_order  = Column(Float, default=0.0)

    portfolio = relationship("Portfolio", back_populates="members")
    project   = relationship("Project")
