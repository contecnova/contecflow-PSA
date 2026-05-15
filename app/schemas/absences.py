from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class AbsenceIn(BaseModel):
    type: str = Field(..., description="Tipo de ausencia (vacaciones, baja, permiso, etc.)")
    start_date: date = Field(..., description="Fecha de inicio de la ausencia")
    end_date: date = Field(..., description="Fecha de fin de la ausencia")
    reason: Optional[str] = Field(None, description="Motivo o justificación de la ausencia")


class AbsenceReview(BaseModel):
    approved: bool = Field(..., description="Indica si la ausencia ha sido aprobada")
    rejection_reason: Optional[str] = Field(None, description="Motivo del rechazo en caso de no ser aprobada")
