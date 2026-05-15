"""
Time Tracking Schemas.
Support for timers, retroactive blocking, and alerts.
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, date


# ── Timer Schemas ──────────────────────────────────────────────────────────

class TimerSessionOut(BaseModel):
    id: str
    user_id: str = Field(..., description="ID del usuario propietario del timer")
    task_id: Optional[str] = Field(None, description="ID de la tarea asociada al timer")
    task_name: Optional[str] = Field(None, description="Nombre de la tarea asociada")
    project_id: str = Field(..., description="ID del proyecto asociado al timer")
    project_name: Optional[str] = Field(None, description="Nombre del proyecto asociado")
    started_at: datetime = Field(..., description="Marca temporal de inicio del timer")
    paused_at: Optional[datetime] = Field(None, description="Marca temporal de pausa actual")
    paused_duration_secs: int = Field(..., description="Total de segundos acumulados en pausa")
    ended_at: Optional[datetime] = Field(None, description="Marca temporal de fin del timer")
    total_elapsed_seconds: Optional[int] = Field(None, description="Segundos transcurridos efectivos calculados")

    class Config:
        from_attributes = True


class TimerStartPayload(BaseModel):
    task_id: Optional[str] = Field(None, description="ID de la tarea para la que se inicia el timer")
    project_id: str = Field(..., description="ID del proyecto para el que se inicia el timer")


class TimerStopPayload(BaseModel):
    description: Optional[str] = Field(None, description="Descripción del trabajo realizado durante el timer")
    is_billable: bool = Field(True, description="Indica si las horas serán facturables")
    task_id: Optional[str] = Field(None, description="ID de la tarea final a la que imputar el tiempo")
    force_duplicate: bool = Field(False, description="Fuerza la creación aunque ya exista una imputación similar")


# ── Imputation Alert Schemas ───────────────────────────────────────────────

class ImputationAlertOut(BaseModel):
    id: str
    user_id: str = Field(..., description="ID del usuario al que se notifica la alerta")
    alert_date: date = Field(..., description="Fecha a la que hace referencia la alerta")
    alert_type: str = Field(..., description="Tipo de alerta de imputación")
    created_at: datetime
    dismissed_at: Optional[datetime] = Field(None, description="Marca temporal en que el usuario descartó la alerta")

    class Config:
        from_attributes = True


# ── Imputation Snapshot Schemas ────────────────────────────────────────────

class ImputationSnapshotOut(BaseModel):
    user_id: str = Field(..., description="ID del usuario del snapshot")
    snapshot_date: date = Field(..., description="Fecha del snapshot")
    total_hours: float = Field(..., description="Total de horas imputadas en la fecha")
    billable_hours: float = Field(..., description="Horas facturables del snapshot")
    approved_hours: float = Field(..., description="Horas aprobadas del snapshot")
    is_complete: bool = Field(..., description="Indica si el snapshot está completo")

    class Config:
        from_attributes = True


# ── Lockout Status Schemas ─────────────────────────────────────────────────

class LockoutStatusOut(BaseModel):
    lockout_days: int = Field(..., description="Días retroactivos permitidos para imputar")
    current_date: date = Field(..., description="Fecha actual de referencia")
    lockout_cutoff_date: date = Field(..., description="Fecha de corte a partir de la cual se bloquean imputaciones")
    locked_date_ranges: list = Field(..., description="Rangos de fechas bloqueadas (anteriores al cutoff)")
    editable_date_ranges: list = Field(..., description="Rangos de fechas editables (posteriores al cutoff)")


class ImputationAnalytics(BaseModel):
    """Daily/weekly/monthly summaries."""
    period: str = Field(..., description="Periodo del análisis (daily, weekly, monthly)")
    total_hours: float = Field(..., description="Total de horas imputadas en el periodo")
    billable_hours: float = Field(..., description="Horas facturables del periodo")
    approved_hours: float = Field(..., description="Horas aprobadas del periodo")
    by_project: dict = Field(..., description="Desglose por proyecto {project_id: {hours, billable, approved}}")
    by_task: dict = Field(..., description="Desglose por tarea {task_id: {hours, billable, approved}}")
