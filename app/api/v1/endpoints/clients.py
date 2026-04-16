"""
Clients — Entidad central del sistema.
Un cliente puede tener: proyectos, contratos, licencias ALM, activos,
usuarios de portal y acceso al Service Desk independientemente de
si tiene proyectos vinculados.
"""
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from typing import Optional
from app.db.session import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.services.client_service import (
    get_client_detail as _out_detail,
    create_portal_user as svc_create_portal_user,
    get_scoped_client_or_404 as _get_scoped_client_or_404,
    create_client_record as svc_create_client,
    get_client_360 as svc_client_360,
)
import app.services.client_service as _svc

router = APIRouter()


# ── CRUD principal ─────────────────────────────────────────────────────────────

@router.get("")
def list_clients(
    q: Optional[str] = None,
    status: Optional[str] = None,
    industry: Optional[str] = None,
    limit: Optional[int] = None,
    db: Session = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    return _svc.list_clients(db, cu, q=q, status=status, industry=industry, limit=limit)


@router.post("")
def create_client(data: dict = Body(...), db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return svc_create_client(data, cu, db)


@router.get("/{cid}")
def get_client(cid: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    cu = _
    c = _get_scoped_client_or_404(db, cu, cid)
    return _out_detail(c, db)


@router.patch("/{cid}")
def update_client(cid: str, data: dict = Body(...), db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return _svc.update_client(cid, data, cu, db)


@router.delete("/{cid}")
def delete_client(cid: str, db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return _svc.delete_client(cid, cu, db)


# ── Contactos ─────────────────────────────────────────────────────────────────

@router.get("/{cid}/contacts")
def list_contacts(cid: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return _svc.list_contacts(cid, db)


@router.post("/{cid}/contacts")
def add_contact(cid: str, data: dict = Body(...), db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return _svc.add_contact(cid, data, db)


@router.patch("/{cid}/contacts/{contact_id}")
def update_contact(cid: str, contact_id: str, data: dict = Body(...),
                   db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return _svc.update_contact(cid, contact_id, data, db)


@router.delete("/{cid}/contacts/{contact_id}")
def delete_contact(cid: str, contact_id: str, db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return _svc.delete_contact(cid, contact_id, db)


# ── Vinculación de licencias ───────────────────────────────────────────────────

@router.get("/{cid}/licenses")
def list_client_licenses(cid: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return _svc.list_client_licenses(cid, db)


@router.post("/{cid}/licenses")
def link_license(cid: str, data: dict = Body(...), db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return _svc.link_license(cid, data, db)


@router.delete("/{cid}/licenses/{link_id}")
def unlink_license(cid: str, link_id: str, db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return _svc.unlink_license(cid, link_id, db)


# ── Vinculación de contratos ───────────────────────────────────────────────────

@router.get("/{cid}/contracts")
def list_client_contracts(cid: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return _svc.list_client_contracts(cid, db)


@router.post("/{cid}/contracts")
def link_contract(cid: str, data: dict = Body(...), db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return _svc.link_contract(cid, data, db)


@router.delete("/{cid}/contracts/{link_id}")
def unlink_contract(cid: str, link_id: str, db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return _svc.unlink_contract(cid, link_id, db)


# ── Config portal ─────────────────────────────────────────────────────────────

@router.get("/{cid}/portal-config")
def get_portal_config(cid: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return _svc.get_portal_config(cid, db)


@router.patch("/{cid}/portal-config")
def update_portal_config(cid: str, data: dict = Body(...), db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return _svc.update_portal_config(cid, data, db)


# ── Facturas del cliente ──────────────────────────────────────────────────────

@router.get("/{cid}/invoices")
def list_client_invoices(
    cid: str,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    return _svc.list_client_invoices(cid, db)


# ── Tickets del cliente ────────────────────────────────────────────────────────

@router.get("/{cid}/tickets")
def list_client_tickets(
    cid: str,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    return _svc.list_client_tickets(cid, status, db)


# ── Usuarios de portal del cliente ────────────────────────────────────────────

@router.get("/{cid}/portal-users")
def list_portal_users(cid: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    _get_scoped_client_or_404(db, _, cid)
    return _svc.list_portal_users(cid, db)


@router.post("/{cid}/portal-users")
def create_portal_user(cid: str, data: dict = Body(...), db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    _get_scoped_client_or_404(db, cu, cid)
    return svc_create_portal_user(cid, data, cu, db)


@router.patch("/{cid}/portal-users/{uid}")
def update_portal_user(cid: str, uid: str, data: dict = Body(...),
                       db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return _svc.update_portal_user(cid, uid, data, db)



# ── Vinculación de proyectos ───────────────────────────────────────────────────

@router.get("/{cid}/projects")
def list_client_projects(cid: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return _svc.list_client_projects(cid, db)


@router.get("/{cid}/projects/available")
def list_available_projects(cid: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    try:
        return _svc.list_available_projects(cid, db)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error al cargar proyectos: {str(e)}")


@router.post("/{cid}/projects/{project_id}/link")
def link_project(cid: str, project_id: str, db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return _svc.link_project(cid, project_id, db)


@router.delete("/{cid}/projects/{project_id}/link")
def unlink_project(cid: str, project_id: str, db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return _svc.unlink_project(cid, project_id, db)

# ── Visión 360: resumen ejecutivo del cliente ─────────────────────────────────

@router.get("/{cid}/360")
def client_360(cid: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Vista 360 del cliente: KPIs, actividad reciente, estado de salud."""
    return svc_client_360(cid, db)
