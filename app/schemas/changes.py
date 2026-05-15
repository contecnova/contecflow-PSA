from typing import Optional

from pydantic import BaseModel, Field


class CRIn(BaseModel):
    title: str = Field(..., description="Título de la solicitud de cambio")
    description: str = Field(..., description="Descripción detallada del cambio solicitado")
    justification: Optional[str] = Field(None, description="Justificación del cambio")
    impact: str = Field("medium", description="Nivel de impacto del cambio (low, medium, high, critical)")
    cost_impact: Optional[float] = Field(None, description="Impacto económico estimado")
    schedule_impact_days: Optional[int] = Field(None, description="Impacto en días sobre el cronograma")
    scope_impact: Optional[str] = Field(None, description="Descripción del impacto sobre el alcance")


class CRReview(BaseModel):
    approved: bool = Field(..., description="Indica si la solicitud de cambio se aprueba")
    resolution_notes: Optional[str] = Field(None, description="Notas de la resolución de la revisión")


class ChangeRequestOut(BaseModel):
    id: str
    code: str = Field(..., description="Código identificativo de la solicitud de cambio")
    project_id: str = Field(..., description="ID del proyecto al que pertenece el cambio")
    title: str = Field(..., description="Título de la solicitud de cambio")
    description: str = Field(..., description="Descripción detallada del cambio")
    justification: Optional[str] = Field(None, description="Justificación del cambio")
    impact: str = Field(..., description="Nivel de impacto del cambio")
    impact_label: str = Field("", description="Etiqueta traducida del impacto")
    impact_color: str = Field("#7a8aaa", description="Color asociado al nivel de impacto")
    cost_impact: Optional[float] = Field(None, description="Impacto económico estimado")
    schedule_impact_days: Optional[int] = Field(None, description="Impacto en días sobre el cronograma")
    scope_impact: Optional[str] = Field(None, description="Descripción del impacto sobre el alcance")
    status: str = Field(..., description="Estado actual de la solicitud")
    status_label: str = Field("", description="Etiqueta traducida del estado")
    status_color: str = Field("#7a8aaa", description="Color asociado al estado")
    requested_by: Optional[str] = Field(None, description="ID del usuario solicitante")
