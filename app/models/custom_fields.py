"""
Contecflow v18 — Modelos adicionales para:
  1. Campos personalizados por proyecto (extiende CustomField)
  2. Workflows personalizados (estados + transiciones por proyecto)
  3. Permisos granulares por proyecto (ya en enterprise.py — solo helpers aquí)
"""
import uuid
from sqlalchemy import Column, String, Boolean, Integer, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base


# ══════════════════════════════════════════════════════════════════════════════
# WORKFLOWS PERSONALIZADOS
# ══════════════════════════════════════════════════════════════════════════════

class WorkflowState(Base):
    """Un estado dentro de un workflow personalizado de proyecto."""
    __tablename__ = "workflow_states"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id  = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    name        = Column(String(100), nullable=False)       # "En revisión QA"
    value       = Column(String(50), nullable=False)        # "qa_review"
    color       = Column(String(20), default="#7a8aaa")     # hex color
    icon        = Column(String(10), nullable=True)         # emoji
    is_initial  = Column(Boolean, default=False)            # estado de inicio
    is_final    = Column(Boolean, default=False)            # estado de cierre (cuenta como completado)
    sort_order  = Column(Integer, default=0)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())

    transitions_from = relationship("WorkflowTransition", foreign_keys="WorkflowTransition.from_state_id", back_populates="from_state", cascade="all, delete-orphan")
    transitions_to   = relationship("WorkflowTransition", foreign_keys="WorkflowTransition.to_state_id",   back_populates="to_state")


class WorkflowTransition(Base):
    """Transición permitida entre dos estados de un workflow."""
    __tablename__ = "workflow_transitions"

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id      = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    from_state_id   = Column(String(36), ForeignKey("workflow_states.id", ondelete="CASCADE"), nullable=False)
    to_state_id     = Column(String(36), ForeignKey("workflow_states.id", ondelete="CASCADE"), nullable=False)
    label           = Column(String(100), nullable=True)           # "Enviar a QA"
    required_role   = Column(String(50), nullable=True)            # solo este rol puede ejecutar
    requires_comment= Column(Boolean, default=False)               # obliga a añadir comentario
    created_at      = Column(DateTime(timezone=True), server_default=func.now())

    from_state = relationship("WorkflowState", foreign_keys=[from_state_id], back_populates="transitions_from")
    to_state   = relationship("WorkflowState", foreign_keys=[to_state_id],   back_populates="transitions_to")


# ══════════════════════════════════════════════════════════════════════════════
# CAMPOS PERSONALIZADOS EXTENDIDOS (por proyecto)
# ══════════════════════════════════════════════════════════════════════════════

class ProjectCustomField(Base):
    """Campo personalizado específico de un proyecto (extiende CustomField global)."""
    __tablename__ = "project_custom_fields"

    id            = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id    = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    name          = Column(String(100), nullable=False)
    field_key     = Column(String(50), nullable=False)
    field_type    = Column(String(20), nullable=False)   # text|number|date|select|url|user|boolean
    options       = Column(Text, nullable=True)          # JSON array para select
    is_required   = Column(Boolean, default=False)
    show_in_list  = Column(Boolean, default=True)        # mostrar en tabla de tareas
    sort_order    = Column(Integer, default=0)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())


class ProjectCustomFieldValue(Base):
    """Valor de un campo personalizado de proyecto para una tarea concreta."""
    __tablename__ = "project_custom_field_values"

    id         = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    field_id   = Column(String(36), ForeignKey("project_custom_fields.id", ondelete="CASCADE"), nullable=False)
    task_id    = Column(String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    value      = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    field = relationship("ProjectCustomField", viewonly=True)
