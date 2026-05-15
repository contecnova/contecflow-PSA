from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field

class CalendarEventCreate(BaseModel):
    subject: str = Field(..., description="Asunto del evento de calendario")
    start_dt: datetime = Field(..., description="Fecha y hora de inicio del evento")
    end_dt: datetime = Field(..., description="Fecha y hora de fin del evento")
    body: Optional[str] = Field(None, description="Cuerpo o descripción del evento")
    location: Optional[str] = Field(None, description="Ubicación física o virtual del evento")
    attendees: List[str] = Field([], description="Lista de emails (UPN) de los asistentes")
    user_upn: str = Field(..., description="UPN del usuario propietario del calendario")

class TeamsNotification(BaseModel):
    title: str = Field(..., description="Título de la notificación en Teams")
    text: str = Field(..., description="Texto de la notificación")
    color: str = Field("0078D4", description="Color de la tarjeta en formato hexadecimal")
    webhook_url: Optional[str] = Field(None, description="URL del webhook de Teams destino")

class MilestoneSyncRequest(BaseModel):
    user_upn: str = Field(..., description="UPN del usuario al que sincronizar los hitos")
    days_ahead: int = Field(30, description="Días hacia adelante a considerar para la sincronización")
