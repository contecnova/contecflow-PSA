"""
Contecflow v20 — Módulos:
  1. Tipos de issue custom por proyecto (IssueType + campos por tipo)
  2. Dependencias visuales entre tareas (mejora UI sobre TaskDependency v13)
  3. Búsqueda full-text unificada (FTSIndex sobre tareas, tickets, wiki, épicas)
  4. Dependencias entre épicas visuales (EpicDependency ya existe en v19,
     aquí añadimos metadatos: tipo de dependencia, lag days)
"""
import uuid
import enum
from sqlalchemy import Column, String, Boolean, Integer, Text, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base


# ══════════════════════════════════════════════════════════════════════════════
# 1. TIPOS DE ISSUE CUSTOM POR PROYECTO
# ══════════════════════════════════════════════════════════════════════════════

class IssueType(Base):
    """Tipo de issue definido por proyecto (historia, bug, tarea, mejora, épica, etc.)"""
    __tablename__ = "issue_types"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    project_id   = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    name         = Column(String(100), nullable=False)      # "Historia de usuario"
    value        = Column(String(50),  nullable=False)      # "story"
    icon         = Column(String(10),  nullable=True)       # emoji
    color        = Column(String(20),  default="#7a8aaa")
    description  = Column(String(500), nullable=True)
    is_subtask   = Column(Boolean, default=False)           # puede ser subtarea
    sort_order   = Column(Integer, default=0)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
    is_active    = Column(Boolean, default=True, nullable=False, server_default="1", index=True)  # audit #36 soft-delete

    fields       = relationship("IssueTypeField", back_populates="issue_type",
                                cascade="all, delete-orphan")


class IssueTypeField(Base):
    """Campo custom requerido para un tipo de issue concreto."""
    __tablename__ = "issue_type_fields"

    id             = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    issue_type_id  = Column(String(36), ForeignKey("issue_types.id", ondelete="CASCADE"), nullable=False, index=True)
    field_key      = Column(String(50), nullable=False)   # referencia a project_custom_fields
    is_required    = Column(Boolean, default=False)
    sort_order     = Column(Integer, default=0)

    issue_type = relationship("IssueType", back_populates="fields")


# ══════════════════════════════════════════════════════════════════════════════
# 2. DEPENDENCIAS ENTRE TAREAS — METADATOS ADICIONALES
# ══════════════════════════════════════════════════════════════════════════════

class TaskDepType(str, enum.Enum):
    blocks       = "blocks"        # A bloquea a B (B no puede empezar hasta que A acabe)
    blocked_by   = "blocked_by"    # A está bloqueada por B
    relates_to   = "relates_to"    # relacionadas sin bloqueo
    duplicates   = "duplicates"    # A duplica a B
    cloned_from  = "cloned_from"   # A fue clonada de B


class TaskDependencyMeta(Base):
    """Metadatos adicionales sobre las dependencias de tareas (v13 ya tiene la tabla base)."""
    __tablename__ = "task_dependency_meta"

    id            = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    # Referencia a la dependencia existente en v13
    from_task_id  = Column(String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    to_task_id    = Column(String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    dep_type      = Column(Enum(TaskDepType), default=TaskDepType.blocks, nullable=False)
    lag_days      = Column(Integer, default=0)    # días de retraso tras finalizar
    note          = Column(String(500), nullable=True)
    created_by    = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())


# ══════════════════════════════════════════════════════════════════════════════
# 3. DEPENDENCIAS ENTRE ÉPICAS — METADATOS
# ══════════════════════════════════════════════════════════════════════════════

class EpicDepType(str, enum.Enum):
    finish_to_start  = "finish_to_start"   # B no empieza hasta que A termine (default Gantt)
    start_to_start   = "start_to_start"    # B no empieza hasta que A empiece
    finish_to_finish = "finish_to_finish"  # B no termina hasta que A termine
    relates_to       = "relates_to"        # sin bloqueo, solo relacionadas


class EpicDependencyMeta(Base):
    """Metadatos de tipo y lag para dependencias entre épicas."""
    __tablename__ = "epic_dependency_meta"

    id            = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    epic_id       = Column(String(36), ForeignKey("epics.id", ondelete="CASCADE"), nullable=False, index=True)
    depends_on_id = Column(String(36), ForeignKey("epics.id", ondelete="CASCADE"), nullable=False)
    dep_type      = Column(Enum(EpicDepType), default=EpicDepType.finish_to_start)
    lag_days      = Column(Integer, default=0)
    created_by    = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())


# ══════════════════════════════════════════════════════════════════════════════
# 4. ÍNDICE DE BÚSQUEDA FULL-TEXT UNIFICADO
# ══════════════════════════════════════════════════════════════════════════════

class FTSEntry(Base):
    """Índice de búsqueda full-text sobre todas las entidades del sistema."""
    __tablename__ = "fts_index"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    entity_type = Column(String(30), nullable=False, index=True)  # task, ticket, wiki_page, epic, project, comment
    entity_id   = Column(String(36), nullable=False, index=True)
    project_id  = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    title       = Column(Text, nullable=True)
    body        = Column(Text, nullable=True)   # contenido completo normalizado
    tags        = Column(Text, nullable=True)   # keywords extra
    updated_at  = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
