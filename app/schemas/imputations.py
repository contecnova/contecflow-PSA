from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from app.schemas.projects import ProjectSummary
from app.schemas.tasks import TaskOut
from app.schemas.users import UserPublic


class ImputationCreate(BaseModel):
    task_id: Optional[str] = Field(default=None, description="ID de la tarea asociada a la imputación")
    project_id: str = Field(..., description="ID del proyecto al que se imputan las horas")
    date: date = Field(..., description="Fecha de la imputación")
    hours: float = Field(..., gt=0, le=24, description="Horas imputadas (mayor que 0 y máximo 24)")
    description: Optional[str] = Field(default=None, description="Descripción del trabajo imputado")
    is_billable: bool = Field(default=False, description="Indica si la imputación es facturable")
    force_duplicate: bool = Field(default=False, description="Fuerza la creación aunque ya exista una imputación similar")

    @field_validator("hours")
    @classmethod
    def hours_precision(cls, v: float) -> float:
        return round(v * 2) / 2


class ImputationUpdate(BaseModel):
    hours: Optional[float] = Field(None, gt=0, le=24, description="Horas (debe ser positivo, max 24)")
    description: Optional[str] = Field(default=None, description="Descripción del trabajo imputado")
    is_billable: Optional[bool] = Field(default=None, description="Indica si la imputación es facturable")


class ImputationOut(BaseModel):
    id: str = Field(..., description="Identificador único de la imputación")
    user: UserPublic = Field(..., description="Usuario que realizó la imputación")
    task: Optional[TaskOut] = Field(default=None, description="Tarea asociada a la imputación")
    project: Optional[ProjectSummary] = Field(default=None, description="Resumen del proyecto asociado")
    date: date = Field(..., description="Fecha de la imputación")
    hours: float = Field(..., description="Horas imputadas")
    cost_amount: Optional[float] = Field(default=None, description="Coste calculado de la imputación en euros")
    description: Optional[str] = Field(default=None, description="Descripción del trabajo imputado")
    is_billable: bool = Field(..., description="Indica si la imputación es facturable")
    is_approved: bool = Field(..., description="Indica si la imputación ha sido aprobada")
    is_invoiced: bool = Field(default=False, description="Indica si la imputación ha sido facturada")
    invoiced_invoice_id: Optional[str] = Field(default=None, description="ID de la factura que incluye esta imputación")
    timer_session_id: Optional[str] = Field(default=None, description="ID de la sesión de cronómetro asociada")
    created_at: datetime = Field(..., description="Fecha de creación de la imputación")

    class Config:
        from_attributes = True


class WeekSummary(BaseModel):
    user_id: str = Field(..., description="ID del usuario al que pertenece el resumen")
    week_start: date = Field(..., description="Fecha de inicio de la semana")
    week_end: date = Field(..., description="Fecha de fin de la semana")
    total_hours: float = Field(..., description="Total de horas imputadas en la semana")
    capacity_hours: float = Field(..., description="Capacidad de horas planificada para la semana")
    load_pct: float = Field(..., description="Porcentaje de carga sobre la capacidad")
    by_project: List[dict] = Field(..., description="Desglose de horas por proyecto")
    by_day: List[dict] = Field(..., description="Desglose de horas por día")
