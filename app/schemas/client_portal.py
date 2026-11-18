"""Esquemas del portal de clientes compartidos por API y servicios (18-11-2026).

`ClientCreateIn` vivía en el endpoint `app/api/v1/endpoints/client_portal.py`;
dar acceso al portal desde un contacto (`client_service.dar_acceso_al_portal`)
lo necesita también y los servicios no importan `app.api` (arquitectura C4).
"""
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.config import settings


class ClientCreateIn(BaseModel):
    project_id: Optional[str] = None        # Legacy single-project (also added to M2M)
    project_ids: Optional[List[str]] = None # Multi-project access list
    client_org_id: Optional[str] = None     # Empresa cliente (entidad Client)
    full_name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr = Field(..., max_length=120)
    job_title: Optional[str] = Field(None, max_length=80)
    company: Optional[str] = Field(None, max_length=120)
    phone: Optional[str] = Field(None, max_length=30)
    password: str = Field(..., min_length=8, max_length=128)
    can_approve_deliverables: bool = True
    can_request_changes: bool = True
    can_view_budget: bool = True
    can_view_team: bool = False
    language: str = Field(settings.DEFAULT_LANGUAGE, min_length=2, max_length=10)

    @field_validator('full_name')
    @classmethod
    def name_must_have_alpha(cls, v: str) -> str:
        if not any(c.isalpha() for c in v):
            raise ValueError('El nombre debe contener letras')
        return v
