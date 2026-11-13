from typing import Optional, List
from pydantic import BaseModel, Field

class MeetingProcessPayload(BaseModel):
    title: Optional[str] = Field(None, description="Título de la reunión")
    project_id: Optional[str] = Field(None, description="ID del proyecto asociado a la reunión")
    platform: str = Field("upload", description="Plataforma de origen (upload, teams, zoom, meet)")
    transcript: str = Field(..., description="Transcripción literal de la reunión")
    participants: Optional[List[str]] = Field(None, description="Lista de participantes identificados")
    meeting_date: Optional[str] = Field(None, description="Fecha de la reunión en formato ISO")
    duration_min: Optional[int] = Field(None, description="Duración de la reunión en minutos")

class ContractAnalyzePayload(BaseModel):
    project_id: Optional[str] = Field(None, description="ID del proyecto al que se asocia el contrato")
    client_name: Optional[str] = Field(None, description="Nombre del cliente contraparte")
    filename: Optional[str] = Field(None, description="Nombre del archivo original del contrato")
    contract_text: str = Field(..., description="Texto completo del contrato a analizar")

class VoiceCommandPayload(BaseModel):
    transcript: str = Field(..., description="Transcripción del comando de voz")
    confidence: Optional[float] = Field(None, description="Nivel de confianza de la transcripción (0-1)")
    # Si False (default), el comando se interpreta pero NO se ejecuta —
    # devuelve `pending_action` para que el cliente muestre confirmación
    # humana antes de hacer write. Si True, ejecuta directamente.
    confirm: bool = Field(False, description="Si es True ejecuta directamente, si no devuelve acción pendiente de confirmación")

class SmartScheduleRequest(BaseModel):
    project_id: Optional[str] = Field(None, description="ID del proyecto a planificar")
    max_tasks: int = Field(20, description="Número máximo de tareas a considerar en la planificación")
