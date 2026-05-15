from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class MilestoneIn(BaseModel):
    name: str = Field(..., description="Nombre del hito del proyecto")
    description: Optional[str] = Field(None, description="Descripción detallada del hito")
    due_date: Optional[date] = Field(None, description="Fecha objetivo de finalización del hito")
    billing_amount: Optional[float] = Field(None, description="Importe a facturar al cumplir el hito")
    billing_pct: Optional[float] = Field(None, description="Porcentaje del total a facturar al cumplir el hito")
    sort_order: int = Field(0, description="Orden de visualización del hito")


class MilestoneOut(MilestoneIn):
    id: str
    project_id: str = Field(..., description="ID del proyecto al que pertenece el hito")
    is_completed: bool = Field(..., description="Indica si el hito está marcado como completado")
    completed_date: Optional[date] = Field(None, description="Fecha en que se completó el hito")
    is_billed: bool = Field(..., description="Indica si el hito ya ha sido facturado")
    billed_at: Optional[date] = Field(None, description="Fecha en que se facturó el hito")
    model_config = {"from_attributes": True}


class MilestoneUpdate(BaseModel):
    is_completed: Optional[bool] = Field(None, description="Actualiza el estado de completitud")
    completed_date: Optional[date] = Field(None, description="Nueva fecha de completitud")
    is_billed: Optional[bool] = Field(None, description="Actualiza el estado de facturación")
    billed_at: Optional[date] = Field(None, description="Nueva fecha de facturación")
    name: Optional[str] = Field(None, description="Nuevo nombre del hito")
    due_date: Optional[date] = Field(None, description="Nueva fecha objetivo")
    billing_amount: Optional[float] = Field(None, description="Nuevo importe a facturar")


class MilestoneApprovalRequestIn(BaseModel):
    message: Optional[str] = Field(None, description="Mensaje justificativo de la solicitud de aprobación")


class MilestoneApprovalDecisionIn(BaseModel):
    approved: bool = Field(..., description="Indica si la aprobación del hito se concede")
    rejection_reason: Optional[str] = Field(None, description="Motivo del rechazo si no se aprueba")
