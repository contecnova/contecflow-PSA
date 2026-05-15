from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field


class SkillIn(BaseModel):
    name: str = Field(..., description="Nombre de la skill")
    category: str = Field(..., description="Categoría a la que pertenece la skill")
    description: Optional[str] = Field(None, description="Descripción de la skill")


class UserSkillIn(BaseModel):
    skill_id: str = Field(..., description="ID de la skill asignada al usuario")
    level: str = Field(..., description="Nivel de dominio (beginner, intermediate, advanced, expert)")
    years_experience: Optional[float] = Field(None, description="Años de experiencia con la skill")
    certified: bool = Field(False, description="Indica si el usuario está certificado")
    cert_name: Optional[str] = Field(None, description="Nombre de la certificación")
    cert_expiry: Optional[date] = Field(None, description="Fecha de expiración de la certificación")
    notes: Optional[str] = Field(None, description="Notas adicionales sobre la skill del usuario")


class StaffingQuery(BaseModel):
    skill_ids: List[str] = Field(..., description="Lista de IDs de skills requeridas")
    min_level: str = Field("basic", description="Nivel mínimo exigido para todas las skills")
    available_from: Optional[date] = Field(None, description="Fecha mínima de disponibilidad")
    available_weeks: int = Field(1, description="Semanas mínimas de disponibilidad requeridas")
