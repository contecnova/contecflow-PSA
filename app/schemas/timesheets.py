from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class TimesheetOut(BaseModel):
    id: str
    user_id: str = Field(..., description="ID del usuario propietario del timesheet")
    week_start: date = Field(..., description="Fecha de inicio de la semana del timesheet")
    week_end: date = Field(..., description="Fecha de fin de la semana del timesheet")
    status: str = Field(..., description="Estado del timesheet (draft, submitted, approved, rejected)")
    total_hours: float = Field(..., description="Total de horas imputadas en la semana")
    billable_hours: float = Field(..., description="Total de horas facturables en la semana")
    total_cost: float = Field(..., description="Coste total calculado del timesheet")
    submitted_at: Optional[date] = Field(None, description="Fecha en que se envió el timesheet a revisión")
    reviewed_at: Optional[date] = Field(None, description="Fecha en que se revisó el timesheet")
    review_notes: Optional[str] = Field(None, description="Notas del revisor sobre el timesheet")
    user_name: Optional[str] = Field(None, description="Nombre del usuario propietario")
    reviewer_name: Optional[str] = Field(None, description="Nombre del usuario revisor")
    model_config = {"from_attributes": True}

    @field_validator("submitted_at", "reviewed_at", mode="before")
    @classmethod
    def coerce_datetime_to_date(cls, v):
        if isinstance(v, datetime):
            return v.date()
        return v


class TimesheetReview(BaseModel):
    approved: bool = Field(..., description="Indica si el timesheet se aprueba")
    notes: Optional[str] = Field(None, description="Notas explicativas de la revisión")


class ImputationLine(BaseModel):
    id: str
    date: date
    hours: float = Field(..., description="Horas imputadas en la línea")
    billable_hours: float = Field(..., description="Horas facturables de la línea")
    cost: float = Field(..., description="Coste calculado de la imputación")
    project_name: str = Field(..., description="Nombre del proyecto imputado")
    project_code: str = Field(..., description="Código del proyecto imputado")
    description: Optional[str] = Field(None, description="Descripción del trabajo imputado")
    is_billable: bool = Field(..., description="Indica si la línea es facturable")
    is_approved: bool = Field(..., description="Indica si la línea está aprobada")


class TimesheetSendBackPayload(BaseModel):
    notes: str = Field("", description="Notas explicativas del envío de vuelta al usuario")
