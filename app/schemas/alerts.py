from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.projects import ProjectSummary
from app.schemas.users import UserPublic


class AlertOut(BaseModel):
    id: str = Field(..., description="Identificador único de la alerta (UUID)")
    alert_type: str = Field(..., description="Tipo de alerta (ej. budget_overrun, deadline_risk, capacity_overload)")
    severity: str = Field(..., description="Severidad de la alerta (low | medium | high | critical)")
    title: str = Field(..., description="Título breve de la alerta mostrado al usuario")
    description: Optional[str] = Field(None, description="Descripción detallada de la causa o contexto de la alerta")
    value: Optional[float] = Field(None, description="Valor observado que disparó la alerta (ej. horas consumidas)")
    threshold: Optional[float] = Field(None, description="Umbral configurado a partir del cual se dispara la alerta")
    user: Optional[UserPublic] = Field(None, description="Usuario al que va dirigida la alerta (si aplica)")
    project: Optional[ProjectSummary] = Field(None, description="Proyecto al que pertenece la alerta (si aplica)")
    is_read: bool = Field(..., description="Indica si el usuario ya ha leído/visualizado la alerta")
    is_resolved: bool = Field(..., description="Indica si la alerta ya ha sido resuelta o reconocida")
    created_at: datetime = Field(..., description="Fecha y hora en que se generó la alerta")

    class Config:
        from_attributes = True
