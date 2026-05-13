"""Módulo de evaluaciones de rendimiento 360°."""
import uuid
import enum
from sqlalchemy import Column, String, Text, Float, Boolean, ForeignKey, Date, Integer, JSON
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


class Review360CampaignStatus(str, enum.Enum):
    draft   = "draft"    # Recién creada, evaluadores aún no han recibido
    active  = "active"   # Evaluadores reciben sus PerformanceReview pendientes
    closed  = "closed"   # Resultados congelados, dashboard solo lectura


class ReviewCycle(Base):
    """Ciclo de evaluación (trimestral, anual…)."""
    __tablename__ = "review_cycles"
    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
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
    questions   = relationship("ReviewQuestion", back_populates="cycle",
                               cascade="all, delete-orphan",
                               order_by="ReviewQuestion.order")


class QuestionKind(str, enum.Enum):
    rating_5    = "rating_5"      # 1-5
    rating_10   = "rating_10"     # 1-10
    scale_likert = "scale_likert" # 5 puntos: muy en desacuerdo … muy de acuerdo
    yes_no      = "yes_no"        # booleano
    text_short  = "text_short"    # input una línea
    text_long   = "text_long"     # textarea


class ReviewQuestion(Base):
    """Pregunta configurable que vive dentro de un ciclo.

    Cada ciclo posee su propio cuestionario. Al cerrar el ciclo, las preguntas
    quedan congeladas (porque el ciclo es read-only). Para reutilizar, RR.HH.
    puede clonar el cuestionario de un ciclo anterior al crear uno nuevo.
    """
    __tablename__ = "review_questions"
    id        = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    cycle_id  = Column(String(36), ForeignKey("review_cycles.id", ondelete="CASCADE"),
                       nullable=False, index=True)
    # `key` es el identificador estable (snake_case) usado en answers_json
    key       = Column(String(80), nullable=False)
    label     = Column(String(300), nullable=False)
    hint      = Column(String(500), nullable=True)
    kind      = Column(Enum(QuestionKind), nullable=False, default=QuestionKind.rating_5)
    order     = Column(Integer, nullable=False, default=0)
    required  = Column(Boolean, nullable=False, default=False)
    scale_min = Column(Integer, nullable=True)   # solo para rating_*
    scale_max = Column(Integer, nullable=True)
    cycle     = relationship("ReviewCycle", back_populates="questions")


class Review360Campaign(Base):
    """Campaña 360° explícita para una persona dentro de un ciclo.

    Una campaña agrupa varias `PerformanceReview` que comparten reviewee
    (subject) — típicamente self + manager + N pares + N reportes directos.
    El dashboard agregado se construye desde aquí y aplica anonimización
    por grupo cuando hay menos de `anonymity_threshold` evaluadores.
    """
    __tablename__ = "review_360_campaigns"
    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    cycle_id     = Column(String(36), ForeignKey("review_cycles.id", ondelete="CASCADE"),
                          nullable=False, index=True)
    subject_id   = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    status       = Column(Enum(Review360CampaignStatus),
                          default=Review360CampaignStatus.draft, nullable=False)
    # Umbral de anonimización: por debajo de N evaluadores en un grupo, las
    # respuestas individuales no se exponen, solo el agregado del grupo.
    anonymity_threshold = Column(Integer, nullable=False, default=3)
    created_by   = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
    closed_at    = Column(DateTime(timezone=True), nullable=True)

    cycle        = relationship("ReviewCycle", foreign_keys=[cycle_id])
    subject      = relationship("User", foreign_keys=[subject_id])
    reviews      = relationship("PerformanceReview", back_populates="campaign",
                                cascade="all, delete-orphan")


class PerformanceReview(Base):
    """Evaluación individual dentro de un ciclo."""
    __tablename__ = "performance_reviews"
    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    cycle_id     = Column(String(36), ForeignKey("review_cycles.id", ondelete="CASCADE"),
                          nullable=False, index=True)
    # Si la review pertenece a una campaña 360°, este FK la enlaza para
    # construir el dashboard agregado por subject. Las reviews "sueltas"
    # (asignadas una a una desde la UI clásica) lo dejan en NULL.
    campaign_id  = Column(String(36),
                          ForeignKey("review_360_campaigns.id", ondelete="SET NULL"),
                          nullable=True, index=True)
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
    # Texto libre (legacy, se mantiene para retrocompatibilidad de evaluaciones
    # creadas antes de las preguntas configurables).
    strengths    = Column(Text, nullable=True)
    improvements = Column(Text, nullable=True)
    goals_next   = Column(Text, nullable=True)
    # Respuestas a las preguntas dinámicas del ciclo: { "<question.key>": value }
    # Para preguntas tipo rating_* el valor es number; para text_* es string;
    # para yes_no es boolean.
    answers_json = Column(JSON, nullable=False, default=dict)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
    cycle        = relationship("ReviewCycle", back_populates="reviews")
    campaign     = relationship("Review360Campaign", back_populates="reviews",
                                foreign_keys=[campaign_id])
    reviewee     = relationship("User", foreign_keys=[reviewee_id])
    reviewer     = relationship("User", foreign_keys=[reviewer_id])


# ── Development Plan: plan de acción tras un 360° ─────────────────────────────

class DevPlanStatus(str, enum.Enum):
    draft     = "draft"      # Borrador, aún en redacción
    active    = "active"     # Aprobado por el manager y en marcha
    completed = "completed"  # Todos los goals cerrados con éxito
    archived  = "archived"   # Pasado o cancelado


class DevGoalStatus(str, enum.Enum):
    pending     = "pending"
    in_progress = "in_progress"
    done        = "done"
    blocked     = "blocked"
    cancelled   = "cancelled"


class DevelopmentPlan(Base):
    """Plan de desarrollo derivado de un 360° (o creado libremente).

    Captura el siguiente paso del método: qué objetivos concretos asume el
    subject tras leer su feedback, con fechas, responsables y revisiones.
    """
    __tablename__ = "development_plans"
    id            = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    subject_id    = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    # Origen opcional: campaña 360° de la que se derivó (puede ser libre).
    campaign_id   = Column(String(36),
                           ForeignKey("review_360_campaigns.id", ondelete="SET NULL"),
                           nullable=True, index=True)
    cycle_id      = Column(String(36),
                           ForeignKey("review_cycles.id", ondelete="SET NULL"),
                           nullable=True, index=True)
    title         = Column(String(200), nullable=False)
    summary       = Column(Text, nullable=True)
    status        = Column(Enum(DevPlanStatus), default=DevPlanStatus.draft, nullable=False)
    target_date   = Column(Date, nullable=True)
    next_review_at = Column(Date, nullable=True)
    created_by    = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())
    updated_at    = Column(DateTime(timezone=True), onupdate=func.now())

    subject       = relationship("User", foreign_keys=[subject_id])
    campaign      = relationship("Review360Campaign", foreign_keys=[campaign_id])
    cycle         = relationship("ReviewCycle", foreign_keys=[cycle_id])
    goals         = relationship("DevGoal", back_populates="plan",
                                 cascade="all, delete-orphan",
                                 order_by="DevGoal.order")


class DevGoal(Base):
    """Objetivo concreto dentro de un plan de desarrollo."""
    __tablename__ = "dev_goals"
    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    plan_id      = Column(String(36),
                          ForeignKey("development_plans.id", ondelete="CASCADE"),
                          nullable=False, index=True)
    title        = Column(String(200), nullable=False)
    description  = Column(Text, nullable=True)
    status       = Column(Enum(DevGoalStatus), default=DevGoalStatus.pending, nullable=False)
    due_date     = Column(Date, nullable=True)
    progress     = Column(Integer, default=0, nullable=False)  # 0..100
    order        = Column(Integer, default=0, nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
    updated_at   = Column(DateTime(timezone=True), onupdate=func.now())

    plan         = relationship("DevelopmentPlan", back_populates="goals")
