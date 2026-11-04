"""
Semantic Assignment Engine — Contecflow
Motor de asignación semántica inspirado en el clasificador Ficosa.
Funciona de forma standalone (sin dependencias externas pesadas) o
con sentence-transformers si está instalado.

Tablas:
  - sem_profiles   : perfiles de usuarios/grupos (texto de sus skills, historial)
  - sem_embeddings : embeddings precalculados de tickets/tareas resueltos (caché)
  - sem_assignments: historial de asignaciones para retroalimentación
  - sem_feedback   : correcciones manuales (expert cache equivalente)
"""
import uuid
import enum
from sqlalchemy import Index, Column, String, Text, Float, Boolean, Integer, DateTime, ForeignKey, Enum
from sqlalchemy.sql import func
from app.db.base import Base


class SemEngineMode(str, enum.Enum):
    semantic   = "semantic"   # sentence-transformers local (sin API key)
    llm        = "llm"        # proveedor LLM configurado (call_ai)
    hybrid     = "hybrid"     # semantic primero, LLM como fallback
    rules_only = "rules_only" # solo reglas de negocio, sin IA


class SemAssignmentType(str, enum.Enum):
    ticket  = "ticket"
    task    = "task"
    sprint  = "sprint"


class SemProfile(Base):
    """Perfil semántico de un agente/usuario para recibir asignaciones."""
    __tablename__ = "sem_profiles"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    user_id     = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    # Texto libre que describe las capacidades: job_title + skills + departamento + historial
    profile_text= Column(Text, nullable=False, default="")
    # Embedding serializado como JSON (lista de floats)
    embedding   = Column(Text, nullable=True)
    # Stats de carga actual
    open_tickets= Column(Integer, default=0)
    open_tasks  = Column(Integer, default=0)
    # Para balanceo de carga
    max_load    = Column(Integer, default=10)
    is_available= Column(Boolean, default=True)
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    is_active   = Column(Boolean, default=True, nullable=False, server_default="1", index=True)  # audit #36 soft-delete


class SemEmbeddingCache(Base):
    """Embeddings de ítems ya procesados (tickets/tareas) — equivalente al Expert Cache de Ficosa."""
    __tablename__ = "sem_embedding_cache"
    # Unico por organizacion (revision multitenant 2026-11): antes era global y
    # una segunda empresa no podia repetir el codigo/nombre de otra.
    __table_args__ = (Index("uq_sem_embedding_cache_org_text_hash", "organization_id", "text_hash", unique=True),)

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    item_type       = Column(String(20), nullable=False)   # ticket | task
    item_id         = Column(String(36), nullable=False, index=True)
    text_hash       = Column(String(64), nullable=False, index=True)  # SHA-256
    text_snippet    = Column(String(500), nullable=True)
    embedding       = Column(Text, nullable=True)          # JSON list of floats
    assigned_user_id= Column(String(36), nullable=True)    # quién lo resolvió
    resolution_quality = Column(Float, nullable=True)      # CSAT o señal de calidad
    created_at      = Column(DateTime(timezone=True), server_default=func.now())


class SemAssignment(Base):
    """Historial de asignaciones automáticas — para retroalimentación y calibración."""
    __tablename__ = "sem_assignments"

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    item_type       = Column(Enum(SemAssignmentType), nullable=False)
    item_id         = Column(String(36), nullable=False, index=True)
    item_title      = Column(String(500), nullable=True)
    # Resultado de la asignación
    suggested_user_id   = Column(String(36), ForeignKey("users.id"), nullable=True)
    accepted_user_id    = Column(String(36), ForeignKey("users.id"), nullable=True)
    was_accepted        = Column(Boolean, nullable=True)    # None = pendiente, True/False = validado
    # Puntuaciones
    confidence          = Column(Float, nullable=True)
    top_scores          = Column(Text, nullable=True)       # JSON {user_id: score}
    engine_mode         = Column(String(20), nullable=True) # semantic|llm|hybrid
    # Estimación de esfuerzo (para tareas)
    estimated_hours     = Column(Float, nullable=True)
    complexity          = Column(String(20), nullable=True) # simple|medium|complex
    # Metadatos
    reasoning           = Column(Text, nullable=True)
    needs_review        = Column(Boolean, default=False)
    created_at          = Column(DateTime(timezone=True), server_default=func.now())
    created_by          = Column(String(36), nullable=True)


class SemFeedback(Base):
    """Correcciones de experto — equivalente al Expert Cache de Ficosa (nivel 2A/2B)."""
    __tablename__ = "sem_feedback"

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    text_hash       = Column(String(64), nullable=False, index=True)
    text_snippet    = Column(String(500), nullable=True)
    embedding       = Column(Text, nullable=True)
    item_type       = Column(String(20), nullable=False)
    correct_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    corrected_by    = Column(String(36), ForeignKey("users.id"), nullable=True)
    times_used      = Column(Integer, default=1)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())


class SemConfig(Base):
    """Configuración del motor semántico por organización."""
    __tablename__ = "sem_config"

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    engine_mode     = Column(Enum(SemEngineMode), default=SemEngineMode.hybrid)
    # Umbrales (equivalente a thresholds.json de Ficosa)
    threshold_ticket = Column(Float, default=0.55)   # score mínimo para auto-asignar ticket
    threshold_task   = Column(Float, default=0.60)   # score mínimo para auto-asignar tarea
    threshold_expert_cache = Column(Float, default=0.92)  # similitud para usar expert cache
    # Balanceo de carga
    load_balance_weight = Column(Float, default=0.20)  # peso del factor carga en el score final
    # Umbrales por prioridad (sobreescriben threshold_ticket/threshold_task)
    threshold_critical  = Column(Float, default=0.90)   # nunca auto-asignar críticos
    threshold_high      = Column(Float, default=0.72)
    threshold_medium    = Column(Float, default=0.58)
    threshold_low       = Column(Float, default=0.45)
    # Semivida de decaimiento del historial (días; peso = 0.5^(age/half_life))
    history_decay_days  = Column(Float, default=90.0)
    # Auto-asignación
    auto_assign_tickets = Column(Boolean, default=False)  # si True, asigna sin confirmación
    auto_assign_tasks   = Column(Boolean, default=False)
    # Modelo local
    local_model_name    = Column(String(200), default="all-MiniLM-L6-v2")
    # Actualizado
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
