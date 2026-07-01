"""TaskMovementLog — registro de auditoría de movimientos de tareas en Kanban.

Almacena cada cambio de estado de una tarea: quién lo hizo, cuándo, desde qué
columna, hacia qué columna y el motivo opcional.
"""
import uuid

from sqlalchemy import Column, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class TaskMovementLog(Base):
    __tablename__ = "task_movement_logs"

    id            = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    task_id       = Column(String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id    = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    moved_by_id   = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    from_status   = Column(String(50), nullable=True)   # nullable para creación inicial
    to_status     = Column(String(50), nullable=False)
    reason        = Column(Text, nullable=True)          # motivo opcional provisto por el usuario
    moved_at      = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    # Relationships (read-only, sin back_populates para no tocar el modelo Task)
    task          = relationship("Task", foreign_keys=[task_id], lazy="select")
    project       = relationship("Project", foreign_keys=[project_id], lazy="select")
    moved_by      = relationship("User", foreign_keys=[moved_by_id], lazy="select")
