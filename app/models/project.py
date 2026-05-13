from sqlalchemy import Column, String, Float, Integer, DateTime, Enum, Text, ForeignKey, Boolean, Date
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
import uuid
from app.db.base import Base
from app.core.config import settings


class ProjectType(str, enum.Enum):
    development = "development"
    maintenance = "maintenance"
    rd = "rd"
    internal = "internal"
    consulting = "consulting"


class ProjectStatus(str, enum.Enum):
    planning   = "planning"
    active     = "active"
    on_hold    = "on_hold"
    paused     = "paused"
    completed  = "completed"
    closed     = "closed"
    cancelled  = "cancelled"
    archived   = "archived"


class ProjectRisk(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class Project(Base):
    __tablename__ = "projects"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Multi-tenancy: row-level org isolation
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True)

    code = Column(String(20), unique=True, nullable=False, index=True)  # e.g. PRJ-001
    name = Column(String(255), nullable=False)
    description = Column(Text)

    # Classification
    project_type = Column(Enum(ProjectType), nullable=False, index=True)
    status = Column(Enum(ProjectStatus), default=ProjectStatus.planning, nullable=False, index=True)
    risk_level = Column(Enum(ProjectRisk), default=ProjectRisk.low)

    # Client / billing
    client_name = Column(String(255))          # Nombre libre (fallback si no hay client_id)
    client_id   = Column(String(36), ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True)
    department = Column(String(100), nullable=True)  # Internal department
    is_billable = Column(Boolean, default=False)
    billing_rate = Column(Float, nullable=True) # €/hour billed to client
    contract_amount = Column(Float, nullable=True)  # Total contract value €
    billing_type = Column(String(20), default="time_material")  # time_material | fixed_price | hourly_bag | recurring_retainer
    # Recurring retainer fields (only used when billing_type = recurring_retainer)
    retainer_amount = Column(Float, nullable=True)   # Fixed €/month invoiced automatically
    retainer_day    = Column(Integer, nullable=True) # Day of month to generate invoice (1-28)

    # Budget
    budget_hours = Column(Float, nullable=True)
    budget_amount = Column(Float, nullable=True)  # € total budget
    currency = Column(String(3), default=settings.DEFAULT_CURRENCY)

    # Dates
    start_date = Column(Date, nullable=True)
    end_date_planned = Column(Date, nullable=True)
    end_date_real = Column(Date, nullable=True)

    # People
    pm_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)

    # Jira integration
    jira_project_key = Column(String(50), nullable=True)
    jira_board_id = Column(Integer, nullable=True)

    # Tags for filtering
    tags = Column(String(500), nullable=True)  # comma-separated

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    # Optimistic locking (P1-5): incremented on every PATCH
    version = Column(Integer, default=1, nullable=False)

    # Relationships
    organization    = relationship("Organization", foreign_keys=[organization_id])
    project_manager = relationship("User", back_populates="managed_projects", foreign_keys=[pm_id])
    client          = relationship("Client", back_populates="projects", foreign_keys=[client_id])
    phases = relationship("ProjectPhase", back_populates="project", cascade="all, delete-orphan", order_by="ProjectPhase.order")
    tasks   = relationship("Task",          back_populates="project")
    members = relationship("ProjectMember", back_populates="project", cascade="all, delete-orphan")
    imputations = relationship("Imputation", back_populates="project")

    @property
    def total_hours_spent(self):
        # Returns None intentionally — compute via SQL aggregation in the API
        # (see _enrich_project() in projects.py).  Accessing self.imputations
        # here would trigger an N+1 lazy-load for every Project in a list.
        return None

    @property
    def total_cost_spent(self):
        # Returns None intentionally — see total_hours_spent above.
        return None

    def __repr__(self):
        return f"<Project {self.code}: {self.name}>"


class ProjectPhase(Base):
    __tablename__ = "project_phases"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    order = Column(Integer, default=0)

    budget_hours = Column(Float, nullable=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)

    status = Column(Enum(ProjectStatus), default=ProjectStatus.planning)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    project = relationship("Project", back_populates="phases")
    tasks = relationship("Task", back_populates="phase")

    def __repr__(self):
        return f"<Phase {self.name} (project={self.project_id})>"


class ProjectMemberRole(str, enum.Enum):
    lead       = "lead"        # Tech lead / responsable técnico
    developer  = "developer"   # Desarrollador
    designer   = "designer"    # Diseñador UX/UI
    qa         = "qa"          # QA / tester
    analyst    = "analyst"     # Analista funcional
    devops     = "devops"      # DevOps / infraestructura
    stakeholder= "stakeholder" # Stakeholder / interesado
    other      = "other"       # Otro


class ProjectMember(Base):
    """Miembros explícitos asignados a un proyecto."""
    __tablename__ = "project_members"

    id         = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id    = Column(String(36), ForeignKey("users.id",    ondelete="CASCADE"), nullable=False, index=True)
    is_active  = Column(Boolean, default=True)
    role       = Column(Enum(ProjectMemberRole), default=ProjectMemberRole.developer)
    allocation_pct = Column(Integer, default=100)   # % de dedicación 1-100
    start_date = Column(Date, nullable=True)
    end_date   = Column(Date, nullable=True)
    notes      = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    project = relationship("Project", back_populates="members")
    user    = relationship("User")

