from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class DeliverableIn(BaseModel):
    name: str = Field(..., description="Nombre del entregable")
    description: Optional[str] = Field(None, description="Descripción detallada del entregable")
    format: Optional[str] = Field(None, description="Formato del entregable (pdf, docx, código, etc.)")
    planned_date: Optional[date] = Field(None, description="Fecha planificada de entrega")
    owner_id: Optional[str] = Field(None, description="ID del usuario responsable del entregable")
    client_contact: Optional[str] = Field(None, description="Contacto del cliente que recibe/valida el entregable")
    acceptance_criteria: Optional[str] = Field(None, description="Criterios de aceptación que debe cumplir el entregable")
    milestone_id: Optional[str] = Field(None, description="ID del hito al que está asociado el entregable")
    phase_id: Optional[str] = Field(None, description="ID de la fase del proyecto a la que pertenece el entregable")
    sort_order: int = Field(0, description="Orden de ordenación dentro de la lista de entregables")


class DeliverableUpdate(BaseModel):
    name: Optional[str] = Field(None, description="Nombre del entregable")
    description: Optional[str] = Field(None, description="Descripción detallada del entregable")
    format: Optional[str] = Field(None, description="Formato del entregable (pdf, docx, código, etc.)")
    status: Optional[str] = Field(None, description="Estado actual del entregable (pendiente, en curso, entregado, aceptado, rechazado)")
    planned_date: Optional[date] = Field(None, description="Fecha planificada de entrega")
    delivered_date: Optional[date] = Field(None, description="Fecha real en la que se entregó al cliente")
    accepted_date: Optional[date] = Field(None, description="Fecha en la que el cliente aceptó el entregable")
    owner_id: Optional[str] = Field(None, description="ID del usuario responsable del entregable")
    client_contact: Optional[str] = Field(None, description="Contacto del cliente que recibe/valida el entregable")
    acceptance_criteria: Optional[str] = Field(None, description="Criterios de aceptación que debe cumplir el entregable")
    rejection_reason: Optional[str] = Field(None, description="Motivo del rechazo si el cliente no acepta el entregable")
    document_url: Optional[str] = Field(None, description="URL del documento asociado al entregable")
    sort_order: Optional[int] = Field(None, description="Orden de ordenación dentro de la lista de entregables")
