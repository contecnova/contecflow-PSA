"""Organizaciones: alta, edicion y asignacion de usuarios.

Auditoria 2026-08 (hallazgo 22). Estas rutas vivian en
`app/api/v1/endpoints/mfa.py`, un fichero de 640 lineas con **38 rutas de ocho
dominios** —MFA, organizaciones, Slack, presupuestos, planificacion asistida,
escenarios, PDF y tokens de BI— servidas por un router llamado «mfa».

La mala ubicacion no fue solo desorden: el CRUD de organizaciones estaba
escondido ahi, y por eso nadie noto que a esos endpoints les faltaba la guarda de
superadministrador que su propio `summary` anunciaba. Fue la causa proxima del P0
numero 1 de la auditoria.

**Los paths no han cambiado.** ABAC y GRC derivan el modulo de la ruta, asi que
tocarlos alteraria los permisos en silencio.
"""
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel
from app.db.session import get_db
from app.core.deps import require_superadmin
from app.models.user import User
from app.core.config import settings
from app.core.abac_enforce import enforce_abac
from app.core.responses import APIListResponse, APIResponse
import app.services.organizations_service as _orgs
from app.schemas.auth_payloads import (
    AssignUserOrgIn,
)

router = APIRouter()


# Quitar usuario de organización
@router.delete("/organizations/{org_id}/remove-user/{user_id}", summary="Quitar usuario de organización")
def remove_user_from_org(
    org_id: str,
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    enforce_abac(db, current_user, "organization", org_id, action="delete")
    try:
        return APIResponse.ok(data=_orgs.remove_user_from_org(org_id, user_id, db))
    except ValueError as e:
        msg = str(e)
        if msg.startswith("404:"):
            raise HTTPException(404, msg[4:])
        raise HTTPException(400, msg)


@router.get("/organizations", summary="Listar organizaciones (super-admin)")
def list_organizations(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    return APIListResponse.ok(items=_orgs.list_organizations(db))


class OrgCreate(BaseModel):
    name: str
    slug: str
    plan: str = "starter"
    max_users: int = 25
    max_projects: int = 100
    admin_email: Optional[str] = None
    timezone: str = settings.DEFAULT_TIMEZONE
    locale: str = settings.DEFAULT_LANGUAGE
    primary_color: Optional[str] = None


class OrgUpdate(BaseModel):
    """Tipado explícito de campos editables de una organización.

    El servicio `_orgs.update_organization` ya tenía un whitelist de campos —
    este schema lo hace explícito en el contrato API y previene mass-assignment.
    """
    name: Optional[str] = None
    plan: Optional[str] = None
    max_users: Optional[int] = None
    max_projects: Optional[int] = None
    is_active: Optional[bool] = None
    admin_email: Optional[str] = None
    timezone: Optional[str] = None
    locale: Optional[str] = None
    primary_color: Optional[str] = None
    logo_url: Optional[str] = None
    require_mfa: Optional[bool] = None


@router.post("/organizations", summary="Crear nueva organización (tenant)")
def create_organization(
    payload: OrgCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    try:
        return APIResponse.ok(data=_orgs.create_organization(payload.model_dump(), current_user, db))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/organizations/{org_id}", summary="Detalle de organización")
def get_organization(
    org_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    try:
        return APIResponse.ok(data=_orgs.get_organization(org_id, db))
    except ValueError:
        raise HTTPException(404)


@router.patch("/organizations/{org_id}", summary="Actualizar organización")
def update_organization(
    org_id: str,
    payload: OrgUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    try:
        return APIResponse.ok(data=_orgs.update_organization(org_id, payload.model_dump(exclude_unset=True), db))
    except ValueError:
        raise HTTPException(404)


@router.post("/organizations/{org_id}/assign-user", summary="Asignar usuario a organización")
def assign_user_to_org(
    org_id: str,
    payload: AssignUserOrgIn = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    try:
        return APIResponse.ok(data=_orgs.assign_user_to_org(org_id, payload.user_id, db))
    except ValueError as e:
        msg = str(e)
        if msg.startswith("404:"):
            raise HTTPException(404, msg[4:])
        raise HTTPException(400, msg)
