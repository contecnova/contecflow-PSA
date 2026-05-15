from typing import Optional

from pydantic import BaseModel, Field


class NPSCreate(BaseModel):
    score: int = Field(..., ge=0, le=10, description="Puntuación NPS del cliente entre 0 y 10")
    comment: Optional[str] = Field(None, description="Comentario libre del cliente sobre la valoración")
    respondent: Optional[str] = Field(None, description="Identificación del respondiente que dio la puntuación")
    source: str = Field("manual", description="Origen de la respuesta (manual, email, survey, etc.)")


class HealthSnapshotCreate(BaseModel):
    health_score: float = Field(..., ge=0, le=100, description="Puntuación global de salud del proyecto (0-100)")
    nps_component: Optional[float] = Field(None, description="Componente NPS del health score")
    delivery_component: Optional[float] = Field(None, description="Componente de entrega del health score")
    budget_component: Optional[float] = Field(None, description="Componente presupuestario del health score")
    activity_component: Optional[float] = Field(None, description="Componente de actividad del health score")
    note: Optional[str] = Field(None, description="Nota explicativa del snapshot de salud")
