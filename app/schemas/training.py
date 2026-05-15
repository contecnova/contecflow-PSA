from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class CourseIn(BaseModel):
    title: str = Field(..., description="Título del curso de formación")
    description: Optional[str] = Field(None, description="Descripción del contenido del curso")
    provider: Optional[str] = Field(None, description="Proveedor o plataforma que imparte el curso")
    category: Optional[str] = Field(None, description="Categoría temática del curso")
    duration_h: Optional[float] = Field(None, description="Duración del curso en horas")
    url: Optional[str] = Field(None, description="URL de acceso al curso")
    cost: Optional[float] = Field(None, description="Coste del curso")


class EnrollmentIn(BaseModel):
    course_id: str = Field(..., description="ID del curso al que se inscribe")
    user_id: str = Field(..., description="ID del usuario inscrito")
    status: str = Field("planned", description="Estado de la inscripción (planned, in_progress, completed, dropped)")
    start_date: Optional[date] = Field(None, description="Fecha de inicio del curso")
    end_date: Optional[date] = Field(None, description="Fecha de fin del curso")
    score: Optional[float] = Field(None, description="Puntuación obtenida")
    notes: Optional[str] = Field(None, description="Notas sobre la inscripción")


class CertificationIn(BaseModel):
    user_id: str = Field(..., description="ID del usuario certificado")
    name: str = Field(..., description="Nombre de la certificación")
    issuer: Optional[str] = Field(None, description="Entidad emisora de la certificación")
    cert_id: Optional[str] = Field(None, description="Identificador único de la certificación")
    obtained_at: Optional[date] = Field(None, description="Fecha de obtención de la certificación")
    expires_at: Optional[date] = Field(None, description="Fecha de expiración de la certificación")
    url: Optional[str] = Field(None, description="URL de verificación de la certificación")
    notes: Optional[str] = Field(None, description="Notas adicionales sobre la certificación")
