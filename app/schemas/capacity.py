from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class CapacityPlanIn(BaseModel):
    user_id: str = Field(..., description="ID del usuario cuya capacidad se planifica")
    project_id: Optional[str] = Field(None, description="ID del proyecto al que se asignan las horas planificadas")
    week_start: date = Field(..., description="Fecha de inicio de la semana planificada")
    planned_hours: float = Field(..., description="Horas planificadas para la semana")
    notes: Optional[str] = Field(None, description="Notas opcionales sobre la planificación")


class CapacityPlanOut(CapacityPlanIn):
    id: str
    user_name: Optional[str] = Field(None, description="Nombre completo del usuario planificado")
    project_name: Optional[str] = Field(None, description="Nombre del proyecto asociado")
    project_code: Optional[str] = Field(None, description="Código identificativo del proyecto")
    model_config = {"from_attributes": True}
