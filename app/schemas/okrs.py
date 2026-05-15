from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class ObjectiveIn(BaseModel):
    title: str = Field(..., description="Título del objetivo OKR")
    description: Optional[str] = Field(None, description="Descripción detallada del objetivo")
    owner_id: Optional[str] = Field(None, description="ID del usuario responsable del objetivo")
    team_id: Optional[str] = Field(None, description="ID del equipo asociado")
    project_id: Optional[str] = Field(None, description="ID del proyecto asociado")
    period: str = Field("Q1", description="Periodo del OKR (Q1, Q2, Q3, Q4, H1, H2, year)")
    year: int = Field(2025, description="Año al que pertenece el objetivo")
    status: str = Field("draft", description="Estado del objetivo (draft, active, achieved, missed)")


class KeyResultIn(BaseModel):
    objective_id: str = Field(..., description="ID del objetivo al que pertenece el key result")
    title: str = Field(..., description="Título del key result")
    kr_type: str = Field("percentage", description="Tipo de KR (percentage, number, currency, boolean)")
    target_value: float = Field(100, description="Valor objetivo a alcanzar")
    current_value: float = Field(0, description="Valor actual del key result")
    unit: Optional[str] = Field(None, description="Unidad de medida del KR")
    owner_id: Optional[str] = Field(None, description="ID del responsable del KR")
    due_date: Optional[date] = Field(None, description="Fecha límite del KR")
    notes: Optional[str] = Field(None, description="Notas adicionales del KR")


class ObjectiveUpdate(BaseModel):
    title: Optional[str] = Field(None, description="Nuevo título del objetivo")
    description: Optional[str] = Field(None, description="Nueva descripción del objetivo")
    owner_id: Optional[str] = Field(None, description="Nuevo responsable del objetivo")
    team_id: Optional[str] = Field(None, description="Nuevo equipo asociado")
    project_id: Optional[str] = Field(None, description="Nuevo proyecto asociado")
    period: Optional[str] = Field(None, description="Nuevo periodo del OKR")
    year: Optional[int] = Field(None, description="Nuevo año del OKR")
    status: Optional[str] = Field(None, description="Nuevo estado del objetivo")


class KeyResultUpdate(BaseModel):
    title: Optional[str] = Field(None, description="Nuevo título del KR")
    kr_type: Optional[str] = Field(None, description="Nuevo tipo de KR")
    target_value: Optional[float] = Field(None, description="Nuevo valor objetivo")
    current_value: Optional[float] = Field(None, description="Nuevo valor actual")
    unit: Optional[str] = Field(None, description="Nueva unidad de medida")
    owner_id: Optional[str] = Field(None, description="Nuevo responsable del KR")
    due_date: Optional[date] = Field(None, description="Nueva fecha límite")
    notes: Optional[str] = Field(None, description="Nuevas notas")


class OKRCheckinIn(BaseModel):
    value: float = Field(..., description="Valor reportado en el checkin")
    note: Optional[str] = Field(None, description="Nota explicativa del checkin")
