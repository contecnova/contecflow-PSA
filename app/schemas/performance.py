from datetime import date
from typing import Optional, List

from pydantic import BaseModel, Field


class ReviewCycleIn(BaseModel):
    name: str
    description: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    include_self: bool = True
    include_peers: bool = True
    include_manager: bool = True
    # Crear el ciclo con las preguntas por defecto (5 dimensiones + 3 textos)
    seed_default_questions: bool = True
    # O clonar las preguntas de un ciclo previo
    clone_questions_from_cycle_id: Optional[str] = None


class PerformanceReviewIn(BaseModel):
    """Payload de actualización de una evaluación.

    Acepta `answers` (dict <question_key>:<value>) — es el camino moderno —
    además de los campos legacy `score_*`/`strengths`/etc. que se mantienen
    por retrocompatibilidad.
    """
    answers: Optional[dict] = None
    score_quality: Optional[float] = None
    score_delivery: Optional[float] = None
    score_teamwork: Optional[float] = None
    score_leadership: Optional[float] = None
    score_innovation: Optional[float] = None
    score_overall: Optional[float] = None
    strengths: Optional[str] = None
    improvements: Optional[str] = None
    goals_next: Optional[str] = None


class ReviewQuestionIn(BaseModel):
    key: str = Field(..., min_length=1, max_length=80)
    label: str = Field(..., min_length=1, max_length=300)
    hint: Optional[str] = None
    kind: str = Field("rating_5",
        pattern="^(rating_5|rating_10|scale_likert|yes_no|text_short|text_long)$")
    order: Optional[int] = None
    required: bool = False
    scale_min: Optional[int] = None
    scale_max: Optional[int] = None


class ReviewQuestionUpdate(BaseModel):
    label: Optional[str] = None
    hint: Optional[str] = None
    kind: Optional[str] = Field(None,
        pattern="^(rating_5|rating_10|scale_likert|yes_no|text_short|text_long)$")
    order: Optional[int] = None
    required: Optional[bool] = None
    scale_min: Optional[int] = None
    scale_max: Optional[int] = None


class Campaign360In(BaseModel):
    """Crear campaña 360° con todos sus evaluadores en una sola petición."""
    subject_id: str
    self_review: bool = True
    manager_reviewer_id: Optional[str] = None
    peer_reviewer_ids: List[str] = Field(default_factory=list)
    upward_reviewer_ids: List[str] = Field(default_factory=list)
    anonymity_threshold: int = Field(3, ge=1, le=20)
    auto_activate: bool = True


# ── Development Plans ─────────────────────────────────────────────────────────

class DevGoalIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    due_date: Optional[date] = None
    order: Optional[int] = None


class DevGoalUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    status: Optional[str] = Field(None,
        pattern="^(pending|in_progress|done|blocked|cancelled)$")
    due_date: Optional[date] = None
    progress: Optional[int] = Field(None, ge=0, le=100)
    order: Optional[int] = None


class DevPlanIn(BaseModel):
    subject_id: str
    title: str = Field(..., min_length=1, max_length=200)
    summary: Optional[str] = None
    campaign_id: Optional[str] = None
    cycle_id: Optional[str] = None
    target_date: Optional[date] = None
    next_review_at: Optional[date] = None
    goals: List[DevGoalIn] = Field(default_factory=list)


class DevPlanUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    summary: Optional[str] = None
    status: Optional[str] = Field(None,
        pattern="^(draft|active|completed|archived)$")
    target_date: Optional[date] = None
    next_review_at: Optional[date] = None
