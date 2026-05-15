from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class RiskIn(BaseModel):
    title: str = Field(..., description="Título del riesgo identificado")
    description: Optional[str] = Field(None, description="Descripción detallada del riesgo")
    category: Optional[str] = Field(None, description="Categoría del riesgo (técnico, financiero, etc.)")
    probability: str = Field(..., description="Probabilidad cualitativa (low, medium, high, very_high)")
    impact: str = Field(..., description="Impacto cualitativo (low, medium, high, critical)")
    status: str = Field("identified", description="Estado del riesgo (identified, analyzing, mitigated, closed)")
    mitigation_plan: Optional[str] = Field(None, description="Plan de mitigación del riesgo")
    contingency_plan: Optional[str] = Field(None, description="Plan de contingencia si el riesgo se materializa")
    response_type: Optional[str] = Field(None, description="Tipo de respuesta (avoid, transfer, mitigate, accept)")
    owner_id: Optional[str] = Field(None, description="ID del propietario del riesgo")
    review_date: Optional[date] = Field(None, description="Fecha de próxima revisión del riesgo")
    cost_impact_min: Optional[float] = Field(None, description="Impacto económico mínimo estimado")
    cost_impact_max: Optional[float] = Field(None, description="Impacto económico máximo estimado")
    schedule_impact_days: Optional[int] = Field(None, description="Impacto en días sobre el cronograma")
    notes: Optional[str] = Field(None, description="Notas internas adicionales")


class RiskUpdate(RiskIn):
    title: Optional[str] = Field(None, description="Nuevo título del riesgo")
    probability: Optional[str] = Field(None, description="Nueva probabilidad cualitativa")
    impact: Optional[str] = Field(None, description="Nuevo impacto cualitativo")
    closed_date: Optional[date] = Field(None, description="Fecha de cierre del riesgo")
