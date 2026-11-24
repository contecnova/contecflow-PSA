"""Esquemas del portal de clientes compartidos por API y servicios (18-11-2026).

`ClientCreateIn` vivía en el endpoint `app/api/v1/endpoints/client_portal.py`;
dar acceso al portal desde un contacto (`client_service.dar_acceso_al_portal`)
lo necesita también y los servicios no importan `app.api` (arquitectura C4).
"""
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator



class ClientCreateIn(BaseModel):
    project_id: Optional[str] = None        # Legacy single-project (also added to M2M)
    project_ids: Optional[List[str]] = None # Multi-project access list
    client_org_id: Optional[str] = None     # Empresa cliente (entidad Client)
    full_name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr = Field(..., max_length=120)
    job_title: Optional[str] = Field(None, max_length=80)
    company: Optional[str] = Field(None, max_length=120)
    phone: Optional[str] = Field(None, max_length=30)
    # 23-11-2026 (M10 del 04b): opcional. Sin ella, el servidor genera una y se la manda
    # al cliente por correo; nadie del equipo la ve ni la copia.
    # 23-11-2026 (portal_usuarios): con ella, contraseña puesta a mano. La longitud
    # y el resto los decide la política de la empresa (errores con código), no el esquema.
    password: Optional[str] = Field(None, min_length=1, max_length=1024)
    # Solo con `password`: obligar a cambiarla en el primer acceso (la pantalla
    # lo marca por defecto; sin el campo, como antes: no obliga) y mandarla por
    # correo al titular (sin el campo, no se manda).
    must_change_password: Optional[bool] = None
    send_access: Optional[bool] = None
    can_approve_deliverables: bool = True
    can_request_changes: bool = True
    can_view_budget: bool = True
    can_view_team: bool = False
    # Incidencia 5 (23-11-2026): sin idioma, el usuario no tiene preferencia
    # (el portal resuelve: su empresa, el navegador o inglés).
    language: Optional[str] = Field(None, min_length=2, max_length=10)

    @field_validator('full_name')
    @classmethod
    def name_must_have_alpha(cls, v: str) -> str:
        if not any(c.isalpha() for c in v):
            raise ValueError('El nombre debe contener letras')
        return v
