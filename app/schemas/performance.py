from datetime import date
from typing import Optional, List

from pydantic import BaseModel, Field


class ReviewCycleIn(BaseModel):
    name: str = Field(..., description="Nombre del ciclo de evaluación")
    description: Optional[str] = Field(None, description="Descripción del ciclo")
    start_date: Optional[date] = Field(None, description="Fecha de inicio del ciclo")
    end_date: Optional[date] = Field(None, description="Fecha de fin del ciclo")
    include_self: bool = Field(True, description="Incluye autoevaluación del sujeto")
    include_peers: bool = Field(True, description="Incluye evaluación de iguales")
    include_manager: bool = Field(True, description="Incluye evaluación del manager")
    # Crear el ciclo con las preguntas por defecto (5 dimensiones + 3 textos)
    seed_default_questions: bool = Field(True, description="Crea el ciclo con las preguntas por defecto")
    # O clonar las preguntas de un ciclo previo
    clone_questions_from_cycle_id: Optional[str] = Field(None, description="ID de ciclo previo desde el que clonar preguntas")


class PerformanceReviewIn(BaseModel):
    """Payload de actualización de una evaluación.

    Acepta `answers` (dict <question_key>:<value>) — es el camino moderno —
    además de los campos legacy `score_*`/`strengths`/etc. que se mantienen
    por retrocompatibilidad.
    """
    answers: Optional[dict] = Field(None, description="Respuestas por question_key (camino moderno)")
    score_quality: Optional[float] = Field(None, description="Puntuación de calidad (legacy)")
    score_delivery: Optional[float] = Field(None, description="Puntuación de entrega (legacy)")
    score_teamwork: Optional[float] = Field(None, description="Puntuación de trabajo en equipo (legacy)")
    score_leadership: Optional[float] = Field(None, description="Puntuación de liderazgo (legacy)")
    score_innovation: Optional[float] = Field(None, description="Puntuación de innovación (legacy)")
    score_overall: Optional[float] = Field(None, description="Puntuación global (legacy)")
    strengths: Optional[str] = Field(None, description="Fortalezas identificadas (legacy)")
    improvements: Optional[str] = Field(None, description="Áreas de mejora identificadas (legacy)")
    goals_next: Optional[str] = Field(None, description="Objetivos para el próximo periodo (legacy)")


class ReviewQuestionIn(BaseModel):
    key: str = Field(..., min_length=1, max_length=80, description="Clave técnica de la pregunta")
    label: str = Field(..., min_length=1, max_length=300, description="Texto visible de la pregunta")
    hint: Optional[str] = Field(None, description="Texto de ayuda explicativo")
    kind: str = Field("rating_5",
        pattern="^(rating_5|rating_10|scale_likert|yes_no|text_short|text_long)$",
        description="Tipo de pregunta y formato de respuesta")
    order: Optional[int] = Field(None, description="Orden de visualización de la pregunta")
    required: bool = Field(False, description="Indica si la respuesta es obligatoria")
    scale_min: Optional[int] = Field(None, description="Valor mínimo de la escala")
    scale_max: Optional[int] = Field(None, description="Valor máximo de la escala")


class ReviewQuestionUpdate(BaseModel):
    label: Optional[str] = Field(None, description="Nuevo texto visible de la pregunta")
    hint: Optional[str] = Field(None, description="Nuevo texto de ayuda")
    kind: Optional[str] = Field(None,
        pattern="^(rating_5|rating_10|scale_likert|yes_no|text_short|text_long)$",
        description="Nuevo tipo de pregunta")
    order: Optional[int] = Field(None, description="Nuevo orden de visualización")
    required: Optional[bool] = Field(None, description="Actualiza si la pregunta es obligatoria")
    scale_min: Optional[int] = Field(None, description="Nuevo valor mínimo de la escala")
    scale_max: Optional[int] = Field(None, description="Nuevo valor máximo de la escala")


class Campaign360In(BaseModel):
    """Crear campaña 360° con todos sus evaluadores en una sola petición."""
    subject_id: str = Field(..., description="ID del usuario evaluado en la campaña")
    self_review: bool = Field(True, description="Incluye autoevaluación del sujeto")
    manager_reviewer_id: Optional[str] = Field(None, description="ID del manager evaluador")
    peer_reviewer_ids: List[str] = Field(default_factory=list, description="IDs de pares evaluadores")
    upward_reviewer_ids: List[str] = Field(default_factory=list, description="IDs de subordinados evaluadores")
    anonymity_threshold: int = Field(3, ge=1, le=20, description="Umbral mínimo de evaluadores para garantizar anonimato")
    auto_activate: bool = Field(True, description="Activa la campaña automáticamente al crearla")


# ── Development Plans ─────────────────────────────────────────────────────────

class DevGoalIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=200, description="Título del objetivo de desarrollo")
    description: Optional[str] = Field(None, description="Descripción del objetivo")
    due_date: Optional[date] = Field(None, description="Fecha objetivo del goal")
    order: Optional[int] = Field(None, description="Orden de visualización del goal")


class DevGoalUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200, description="Nuevo título del goal")
    description: Optional[str] = Field(None, description="Nueva descripción del goal")
    status: Optional[str] = Field(None,
        pattern="^(pending|in_progress|done|blocked|cancelled)$",
        description="Nuevo estado del goal")
    due_date: Optional[date] = Field(None, description="Nueva fecha objetivo")
    progress: Optional[int] = Field(None, ge=0, le=100, description="Progreso porcentual del goal")
    order: Optional[int] = Field(None, description="Nuevo orden de visualización")


class DevPlanIn(BaseModel):
    subject_id: str = Field(..., description="ID del usuario destinatario del plan")
    title: str = Field(..., min_length=1, max_length=200, description="Título del plan de desarrollo")
    summary: Optional[str] = Field(None, description="Resumen ejecutivo del plan")
    campaign_id: Optional[str] = Field(None, description="ID de la campaña 360 relacionada")
    cycle_id: Optional[str] = Field(None, description="ID del ciclo de evaluación relacionado")
    target_date: Optional[date] = Field(None, description="Fecha objetivo de completitud del plan")
    next_review_at: Optional[date] = Field(None, description="Fecha de la próxima revisión")
    goals: List[DevGoalIn] = Field(default_factory=list, description="Lista de goals del plan")


class DevPlanUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200, description="Nuevo título del plan")
    summary: Optional[str] = Field(None, description="Nuevo resumen ejecutivo del plan")
    status: Optional[str] = Field(None,
        pattern="^(draft|active|completed|archived)$",
        description="Nuevo estado del plan")
    target_date: Optional[date] = Field(None, description="Nueva fecha objetivo de completitud")
    next_review_at: Optional[date] = Field(None, description="Nueva fecha de próxima revisión")
