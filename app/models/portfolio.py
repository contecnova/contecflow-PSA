"""
Portfolio model — agrupa proyectos en carteras con seguimiento RAG y presupuesto consolidado.
"""
import enum
import uuid
from sqlalchemy import Column, String, Float, Text, Enum, ForeignKey, Date, DateTime, func, Boolean, Integer
from sqlalchemy.orm import relationship
from app.db.base import Base
from app.models.money import Money


class PortfolioStatus(str, enum.Enum):
    active   = "active"
    archived = "archived"
    planning = "planning"


class Portfolio(Base):
    __tablename__ = "portfolios"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)  # audit #7
    name        = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status      = Column(Enum(PortfolioStatus), default=PortfolioStatus.active, nullable=False)
    is_active   = Column(Boolean, default=True)

    # Budget aggregation
    budget_total   = Column(Money, nullable=True)   # Total budget envelope (€)
    budget_spent   = Column(Money, nullable=True)   # Snapshot of spent (updated on demand)

    # Owner
    owner_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

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
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)  # audit #7
    portfolio_id = Column(String(36), ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id   = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)

    # Manual RAG override (when not auto-computed from EVM)
    rag_override   = Column(String(10), nullable=True)   # green | yellow | red
    is_active      = Column(Boolean, default=True)
    display_order  = Column(Float, default=0.0)

    portfolio = relationship("Portfolio", back_populates="members")
    project   = relationship("Project")


# ── Intake de propuestas, puntuación y fases (rev. 173, 16-11-2026) ─────────
#
# Una propuesta entra (intake), se puntúa contra los criterios de la empresa
# (peso configurable), pasa fase a fase por el motor de aprobaciones
# (stage-gate: cada fase puede tener su flujo) y, aprobada, se convierte en
# proyecto. La capacidad que pide (`roles_needed`) se compara con la del
# equipo en su ventana de fechas antes de decidir.

#: Estados de una propuesta.
ESTADOS_DE_PROPUESTA = ("draft", "in_review", "in_progress", "approved", "rejected", "converted")


class PortfolioCriterion(Base):
    """Criterio de puntuación de propuestas (valor estratégico, riesgo, ROI…)."""
    __tablename__ = "portfolio_criteria"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    description = Column(Text, nullable=True)
    weight = Column(Float, nullable=False, default=1.0)
    # Un criterio «inverso» puntúa mejor cuanto más bajo (p. ej. el riesgo).
    inverse = Column(Boolean, nullable=False, default=False)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PortfolioGate(Base):
    """Fase del stage-gate. `workflow_id`: el flujo de aprobación que la decide
    (sin él, el flujo por defecto de `portfolio_gate`; sin ninguno, admin o PM)."""
    __tablename__ = "portfolio_gates"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    description = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    workflow_id = Column(String(36), ForeignKey("approval_workflows.id", ondelete="SET NULL"), nullable=True, index=True)
    min_score = Column(Float, nullable=True)       # sin valor: PORTFOLIO_MIN_SCORE_TO_ADVANCE
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PortfolioProposal(Base):
    """Propuesta de proyecto que recorre el intake y las fases."""
    __tablename__ = "portfolio_proposals"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    portfolio_id = Column(String(36), ForeignKey("portfolios.id", ondelete="SET NULL"), nullable=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    requested_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    sponsor_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    client_id = Column(String(36), ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True)
    estimated_budget = Column(Money, nullable=True)
    estimated_hours = Column(Float, nullable=True)
    wanted_start = Column(Date, nullable=True)
    wanted_end = Column(Date, nullable=True)
    roles_needed = Column(Text, nullable=True)      # JSON [{"role": "...", "hours": n}]
    scores = Column(Text, nullable=True)            # JSON {criterion_id: 0..10}
    score = Column(Float, nullable=True)            # 0-100 ponderado
    status = Column(String(20), nullable=False, default="draft", index=True)
    gate_index = Column(Integer, nullable=False, default=0)   # fases ya superadas
    decision_note = Column(Text, nullable=True)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    template_id = Column(String(36), ForeignKey("project_templates.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
