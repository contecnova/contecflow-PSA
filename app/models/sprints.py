"""
Sprint / Scrum models — full Agile sprint management.
"""
from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Text, Integer, Enum, Date, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
import uuid
from app.db.base import Base


class SprintStatus(str, enum.Enum):
    planning   = "planning"    # Not yet started, tasks being added
    active     = "active"      # Currently running
    completed  = "completed"   # Finished and closed
    cancelled  = "cancelled"


class Sprint(Base):
    __tablename__ = "sprints"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    project_id  = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    number      = Column(Integer, nullable=False)          # Sprint 1, Sprint 2…
    name        = Column(String(255), nullable=False)      # "Sprint 1 — Auth module"
    goal        = Column(Text, nullable=True)              # Sprint goal / objetivo
    status      = Column(Enum(SprintStatus), default=SprintStatus.planning, nullable=False, index=True)

    start_date  = Column(Date, nullable=True)
    end_date    = Column(Date, nullable=True)

    # Velocity / stats (computed on close)
    planned_points    = Column(Float, default=0)
    completed_points  = Column(Float, default=0)
    velocity          = Column(Float, nullable=True)       # completed_points / duration_weeks

    # Retrospective
    went_well         = Column(Text, nullable=True)
    to_improve        = Column(Text, nullable=True)
    action_items      = Column(Text, nullable=True)

    created_by  = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())
    closed_at   = Column(DateTime(timezone=True), nullable=True)

    project      = relationship("Project")  # TODO #56: inverse en Project (project.py)
    creator      = relationship("User", foreign_keys=[created_by])  # TODO #56: inverse en User
    # audit #56-57: sprint_tasks iterado SIEMPRE en sprint endpoint (sum points, list tasks)
    # → selectin evita N+1 al listar sprints o calcular velocity.
    sprint_tasks = relationship("SprintTask", back_populates="sprint",
                                cascade="all, delete-orphan",
                                order_by="SprintTask.backlog_order",
                                lazy="selectin")


class SprintTask(Base):
    """Association between a task and a sprint, with backlog ordering."""
    __tablename__ = "sprint_tasks"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    sprint_id    = Column(String(36), ForeignKey("sprints.id", ondelete="CASCADE"), nullable=False, index=True)
    task_id      = Column(String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    is_active    = Column(Boolean, default=True)
    backlog_order = Column(Integer, default=0)             # Order within the sprint backlog
    added_at     = Column(DateTime(timezone=True), server_default=func.now())

    sprint = relationship("Sprint", back_populates="sprint_tasks")
    task   = relationship("Task")  # TODO #56: inverse en Task (task.py)
