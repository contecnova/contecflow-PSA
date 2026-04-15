"""
Clients — Entidad central del sistema.
Un cliente puede tener: proyectos, contratos, licencias ALM, activos,
usuarios de portal y acceso al Service Desk independientemente de
si tiene proyectos vinculados.
"""
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from typing import Optional
from app.db.session import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.core.config import settings
import json
from datetime import date
from app.services.client_service import (
    get_client_summary as _out,
    get_client_detail as _out_detail,
    create_portal_user as svc_create_portal_user,
    scoped_client_query as _scoped_client_query,
    get_scoped_client_or_404 as _get_scoped_client_or_404,
    create_client_record as svc_create_client,
    get_client_360 as svc_client_360,
)

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
    from app.models.clients import Client
    query = _scoped_client_query(db, cu)
    if q:
        query = query.filter(
            Client.name.ilike(f"%{q}%") |
            Client.short_name.ilike(f"%{q}%") |
            Client.contact_email.ilike(f"%{q}%")
        )
    if status:   query = query.filter(Client.status == status)
    if industry: query = query.filter(Client.industry == industry)
    query = query.filter(Client.is_active == True).order_by(Client.name)
    if limit is not None and limit > 0:
        query = query.limit(limit)
    return [_out(c, db) for c in query.all()]


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
    if cu.role not in ('admin', 'pm') and not cu.is_superadmin:
        raise HTTPException(status_code=403, detail="Solo admin o PM pueden editar clientes")
    c = _get_scoped_client_or_404(db, cu, cid)
    for k, v in data.items():
        if hasattr(c, k): setattr(c, k, v if v != "" else None)
    db.commit(); db.refresh(c)
    return _out(c, db)


@router.delete("/{cid}")
def delete_client(cid: str, db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    if cu.role not in ('admin', 'pm') and not cu.is_superadmin:
        raise HTTPException(status_code=403, detail="Solo admin o PM pueden eliminar clientes")
    from app.models.project import Project
    c = _get_scoped_client_or_404(db, cu, cid)
    db.query(Project).filter(Project.client_id == cid).update({"client_id": None})
    c.is_active = False  # Soft delete
    db.commit()
    return {"ok": True}


# ── Contactos ─────────────────────────────────────────────────────────────────

@router.get("/{cid}/contacts")
def list_contacts(cid: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    from app.models.clients import ClientContact
    return [
        {"id": ct.id, "full_name": ct.full_name, "email": ct.email,
         "phone": ct.phone, "job_title": ct.job_title, "role": ct.role,
         "is_primary": ct.is_primary, "notes": ct.notes, "is_active": ct.is_active}
        for ct in db.query(ClientContact).filter(
            ClientContact.client_id == cid, ClientContact.is_active == True
        ).order_by(ClientContact.is_primary.desc()).all()
    ]


@router.post("/{cid}/contacts")
def add_contact(cid: str, data: dict = Body(...), db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    from app.models.clients import Client, ClientContact
    c = db.query(Client).filter(Client.id == cid).first()
    if not c: raise HTTPException(404)
    ct = ClientContact(client_id=cid, **{k: v for k, v in data.items() if hasattr(ClientContact, k)})
    db.add(ct); db.commit(); db.refresh(ct)
    return {"id": ct.id, "full_name": ct.full_name, "email": ct.email,
            "phone": ct.phone, "job_title": ct.job_title, "role": ct.role,
            "is_primary": ct.is_primary}


@router.patch("/{cid}/contacts/{contact_id}")
def update_contact(cid: str, contact_id: str, data: dict = Body(...),
                   db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    from app.models.clients import ClientContact
    ct = db.query(ClientContact).filter(ClientContact.id == contact_id, ClientContact.client_id == cid).first()
    if not ct: raise HTTPException(404)
    for k, v in data.items():
        if hasattr(ct, k): setattr(ct, k, v)
    db.commit(); db.refresh(ct)
    return {"id": ct.id, "full_name": ct.full_name, "email": ct.email, "role": ct.role}


@router.delete("/{cid}/contacts/{contact_id}")
def delete_contact(cid: str, contact_id: str, db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    from app.models.clients import ClientContact
    ct = db.query(ClientContact).filter(ClientContact.id == contact_id, ClientContact.client_id == cid).first()
    if not ct: raise HTTPException(404)
    ct.is_active = False
    db.commit()
    return {"ok": True}


# ── Vinculación de licencias ───────────────────────────────────────────────────

@router.get("/{cid}/licenses")
def list_client_licenses(cid: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Licencias vinculadas al cliente (explícitas via link + directas si ALMLicense tuviera client_id)."""
    from app.models.clients import ClientLicenseLink
    from app.models.alm import ALMLicense
    links = db.query(ClientLicenseLink).filter(ClientLicenseLink.client_id == cid).all()
    linked_ids = set()
    result = []
    for ll in links:
        lic = db.query(ALMLicense).filter(ALMLicense.id == ll.license_id).first()
        if lic:
            linked_ids.add(lic.id)
            result.append({
                "link_id": ll.id, "license_id": lic.id, "name": lic.name,
                "status": lic.status, "expiry_date": str(lic.expiry_date) if lic.expiry_date else None,
                "total_seats": lic.total_seats, "annual_cost": lic.annual_cost,
                "notes": ll.notes, "linked_at": str(ll.linked_at),
            })
    return result


@router.post("/{cid}/licenses")
def link_license(cid: str, data: dict = Body(...), db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    from app.models.clients import Client, ClientLicenseLink
    from app.models.alm import ALMLicense
    if not db.query(Client).filter(Client.id == cid).first(): raise HTTPException(404, "Cliente no encontrado")
    lic_id = data.get("license_id")
    if not lic_id or not db.query(ALMLicense).filter(ALMLicense.id == lic_id).first():
        raise HTTPException(404, "Licencia no encontrada")
    existing = db.query(ClientLicenseLink).filter(
        ClientLicenseLink.client_id == cid, ClientLicenseLink.license_id == lic_id
    ).first()
    if existing: raise HTTPException(409, "Licencia ya vinculada a este cliente")
    ll = ClientLicenseLink(client_id=cid, license_id=lic_id, notes=data.get("notes"))
    db.add(ll); db.commit(); db.refresh(ll)
    return {"link_id": ll.id, "license_id": lic_id, "notes": ll.notes}


@router.delete("/{cid}/licenses/{link_id}")
def unlink_license(cid: str, link_id: str, db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    from app.models.clients import ClientLicenseLink
    ll = db.query(ClientLicenseLink).filter(ClientLicenseLink.id == link_id, ClientLicenseLink.client_id == cid).first()
    if not ll: raise HTTPException(404)
    db.delete(ll); db.commit()
    return {"ok": True}


# ── Vinculación de contratos ───────────────────────────────────────────────────

@router.get("/{cid}/contracts")
def list_client_contracts(cid: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Devuelve contratos vinculados al cliente:
    1. Los explícitamente vinculados via ClientContractLink
    2. Los contratos pipeline que tienen client_id == cid directamente
    """
    from app.models.clients import ClientContractLink
    from app.models.pipeline import Contract

    # Contratos explícitamente vinculados (via link table)
    links = db.query(ClientContractLink).filter(ClientContractLink.client_id == cid).all()
    linked_ids = set()
    result = []
    for cl in links:
        con = db.query(Contract).filter(Contract.id == cl.contract_id).first()
        if con:
            linked_ids.add(con.id)
            result.append({
                "link_id": cl.id, "contract_id": con.id,
                "title": getattr(con, 'title', None) or con.client_name,
                "reference": getattr(con, 'reference', None),
                "status": con.status, "total_amount": con.total_amount,
                "start_date": str(con.start_date) if con.start_date else None,
                "end_date": str(con.end_date) if con.end_date else None,
                "linked_at": str(cl.linked_at),
                "source": "explicit",
            })

    # Contratos pipeline con client_id directo (creados desde ContractsPage)
    direct = db.query(Contract).filter(
        Contract.client_id == cid,
        Contract.id.notin_(linked_ids)
    ).all()
    for con in direct:
        result.append({
            "link_id": None, "contract_id": con.id,
            "title": getattr(con, 'title', None) or con.client_name,
            "reference": getattr(con, 'reference', None),
            "status": con.status, "total_amount": con.total_amount,
            "start_date": str(con.start_date) if con.start_date else None,
            "end_date": str(con.end_date) if con.end_date else None,
            "linked_at": str(con.created_at) if con.created_at else None,
            "source": "direct",
        })

    return result


@router.post("/{cid}/contracts")
def link_contract(cid: str, data: dict = Body(...), db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    from app.models.clients import Client, ClientContractLink
    from app.models.pipeline import Contract
    if not db.query(Client).filter(Client.id == cid).first(): raise HTTPException(404, "Cliente no encontrado")
    con_id = data.get("contract_id")
    if not con_id or not db.query(Contract).filter(Contract.id == con_id).first():
        raise HTTPException(404, "Contrato no encontrado")
    existing = db.query(ClientContractLink).filter(
        ClientContractLink.client_id == cid, ClientContractLink.contract_id == con_id
    ).first()
    if existing: raise HTTPException(409, "Contrato ya vinculado")
    cl = ClientContractLink(client_id=cid, contract_id=con_id)
    db.add(cl); db.commit(); db.refresh(cl)
    return {"link_id": cl.id, "contract_id": con_id}


@router.delete("/{cid}/contracts/{link_id}")
def unlink_contract(cid: str, link_id: str, db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    from app.models.clients import ClientContractLink
    cl = db.query(ClientContractLink).filter(ClientContractLink.id == link_id, ClientContractLink.client_id == cid).first()
    if not cl: raise HTTPException(404)
    db.delete(cl); db.commit()
    return {"ok": True}


# ── Config portal ─────────────────────────────────────────────────────────────

@router.get("/{cid}/portal-config")
def get_portal_config(cid: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    from app.models.clients import ClientPortalConfig
    import json
    cfg = db.query(ClientPortalConfig).filter(ClientPortalConfig.client_id == cid).first()
    if not cfg:
        return {"client_id": cid, "enabled_modules": ["service_desk", "projects"], "sd_without_project": True}
    return {
        "client_id": cid,
        "enabled_modules": json.loads(cfg.enabled_modules) if cfg.enabled_modules else [],
        "sd_without_project": cfg.sd_without_project,
        "sla_tier": cfg.sla_tier,
        "max_portal_users": cfg.max_portal_users,
        "max_open_tickets": cfg.max_open_tickets,
        "logo_url": cfg.logo_url,
        "accent_color": cfg.accent_color,
        "default_language": cfg.default_language or settings.DEFAULT_LANGUAGE,
        "allow_profile_edit": cfg.allow_profile_edit if cfg.allow_profile_edit is not None else True,
        "allow_pwd_change": cfg.allow_pwd_change if cfg.allow_pwd_change is not None else True,
    }


@router.patch("/{cid}/portal-config")
def update_portal_config(cid: str, data: dict = Body(...), db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    from app.models.clients import Client, ClientPortalConfig
    import json
    if not db.query(Client).filter(Client.id == cid).first(): raise HTTPException(404)
    cfg = db.query(ClientPortalConfig).filter(ClientPortalConfig.client_id == cid).first()
    if not cfg:
        cfg = ClientPortalConfig(client_id=cid)
        db.add(cfg)
    for k, v in data.items():
        if k == "enabled_modules": setattr(cfg, k, json.dumps(v))
        elif hasattr(cfg, k) and k not in ("client_id", "id", "created_at", "updated_at"):
            setattr(cfg, k, v)
    db.commit(); db.refresh(cfg)
    return {"ok": True, "enabled_modules": json.loads(cfg.enabled_modules)}


# ── Facturas del cliente ──────────────────────────────────────────────────────

@router.get("/{cid}/invoices")
def list_client_invoices(
    cid: str,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Facturas vinculadas al cliente directamente (client_id) o via sus proyectos."""
    from app.models.billing_reports import Invoice
    from app.models.project import Project

    # Facturas directas con client_id
    direct = db.query(Invoice).filter(Invoice.client_id == cid).all()
    seen_ids = {inv.id for inv in direct}

    # Facturas de proyectos del cliente (sin client_id directo)
    client_projects = db.query(Project).filter(Project.client_id == cid).all()
    project_ids = [p.id for p in client_projects]
    via_project = []
    if project_ids:
        via_project = db.query(Invoice).filter(
            Invoice.project_id.in_(project_ids),
            Invoice.id.notin_(seen_ids)
        ).all()

    all_invoices = direct + via_project
    return [
        {
            "id": inv.id,
            "number": inv.number,
            "status": inv.status,
            "issue_date": str(inv.issue_date) if inv.issue_date else None,
            "due_date": str(inv.due_date) if inv.due_date else None,
            "total_amount": inv.total_amount,
            "project_id": inv.project_id,
            "project_name": inv.project.name if inv.project else None,
            "client_name": inv.client_name,
        }
        for inv in sorted(all_invoices, key=lambda x: x.issue_date or date.min, reverse=True)
    ]


# ── Tickets del cliente ────────────────────────────────────────────────────────

@router.get("/{cid}/tickets")
def list_client_tickets(
    cid: str,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    from app.models.service_desk import Ticket
    q = db.query(Ticket).filter(Ticket.client_id == cid)
    if status: q = q.filter(Ticket.status == status)
    return [
        {"id": t.id, "code": getattr(t, 'code', t.id[:8]), "title": t.title,
         "status": t.status, "priority": t.priority,
         "ticket_type": t.ticket_type,
         "linked_resource_type": t.linked_resource_type,
         "linked_resource_id": t.linked_resource_id,
         "created_at": str(t.created_at),
         "resolved_at": str(t.resolved_at) if t.resolved_at else None}
        for t in q.order_by(Ticket.created_at.desc()).limit(50).all()
    ]


# ── Usuarios de portal del cliente ────────────────────────────────────────────

@router.get("/{cid}/portal-users")
def list_portal_users(cid: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    from app.models.client_portal import ClientUser
    _get_scoped_client_or_404(db, _, cid)
    users = db.query(ClientUser).filter(ClientUser.client_org_id == cid).all()
    return [
        {"id": u.id, "full_name": u.full_name, "email": u.email,
         "job_title": u.job_title, "is_active": u.is_active,
         "project_id": u.project_id,
         "can_approve_deliverables": u.can_approve_deliverables,
         "can_view_budget": u.can_view_budget,
         "last_login": str(u.last_login) if u.last_login else None}
        for u in users
    ]


@router.post("/{cid}/portal-users")
def create_portal_user(cid: str, data: dict = Body(...), db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    _get_scoped_client_or_404(db, cu, cid)
    return svc_create_portal_user(cid, data, cu, db)


@router.patch("/{cid}/portal-users/{uid}")
def update_portal_user(cid: str, uid: str, data: dict = Body(...),
                       db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    from app.models.client_portal import ClientUser
    u = db.query(ClientUser).filter(ClientUser.id == uid, ClientUser.client_org_id == cid).first()
    if not u: raise HTTPException(404)
    for k, v in data.items():
        if hasattr(u, k) and k not in ('id', 'hashed_password', 'client_org_id'):
            setattr(u, k, v)
    db.commit()
    return {"id": u.id, "full_name": u.full_name, "email": u.email, "is_active": u.is_active}



# ── Vinculación de proyectos ───────────────────────────────────────────────────

@router.get("/{cid}/projects")
def list_client_projects(cid: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Proyectos directamente vinculados a este cliente (client_id == cid)."""
    from app.models.project import Project
    # Filtrar en Python para máxima compatibilidad con SQLite/Enum
    projects = db.query(Project).filter(Project.client_id == cid).order_by(Project.name).all()
    return [
        {"id": p.id, "code": p.code, "name": p.name, "status": str(p.status),
         "client_id": p.client_id, "is_linked": True,
         "start_date": str(getattr(p, "start_date", None)) if getattr(p, "start_date", None) else None,
         "end_date": str(getattr(p, "end_date_planned", None) or getattr(p, "end_date", None)) if (getattr(p, "end_date_planned", None) or getattr(p, "end_date", None)) else None}
        for p in projects
    ]


@router.get("/{cid}/projects/available")
def list_available_projects(cid: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Proyectos sin cliente asignado + los ya vinculados a este cliente."""
    try:
        from app.models.project import Project
        # Traer todos los proyectos sin filtros SQL complejos para máxima compatibilidad
        all_projects = db.query(Project).order_by(Project.name).all()
        projects = []
        for p in all_projects:
            cid_val = getattr(p, "client_id", None)
            status_val = str(getattr(p, "status", ""))
            if status_val in ("cancelled", "ProjectStatus.cancelled"):
                continue
            if not cid_val or cid_val == "" or cid_val == cid:
                projects.append(p)
        return [
            {
                "id": p.id,
                "code": getattr(p, "code", ""),
                "name": p.name,
                "status": str(p.status),
                "client_id": getattr(p, "client_id", None),
                "is_linked": getattr(p, "client_id", None) == cid,
                "start_date": str(p.start_date) if getattr(p, "start_date", None) else None,
                "end_date": str(getattr(p, "end_date_planned", None) or getattr(p, "end_date", None)) if (getattr(p, "end_date_planned", None) or getattr(p, "end_date", None)) else None,
            }
            for p in projects
        ]
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error al cargar proyectos: {str(e)}")


@router.post("/{cid}/projects/{project_id}/link")
def link_project(cid: str, project_id: str, db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    """Vincula un proyecto a este cliente. Falla si el proyecto ya está en otro cliente."""
    from app.models.clients import Client
    from app.models.project import Project

    client = db.query(Client).filter(Client.id == cid).first()
    if not client: raise HTTPException(404, "Cliente no encontrado")

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project: raise HTTPException(404, "Proyecto no encontrado")

    # Exclusividad: no puede estar vinculado a otro cliente
    if project.client_id and project.client_id != cid:
        other = db.query(Client).filter(Client.id == project.client_id).first()
        raise HTTPException(409, f"El proyecto ya está vinculado al cliente '{other.name if other else project.client_id}'")

    project.client_id   = cid
    project.client_name = client.name
    db.commit()
    return {"ok": True, "project_id": project_id, "client_id": cid}


@router.delete("/{cid}/projects/{project_id}/link")
def unlink_project(cid: str, project_id: str, db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    """Desvincula un proyecto de este cliente."""
    from app.models.project import Project
    project = db.query(Project).filter(Project.id == project_id, Project.client_id == cid).first()
    if not project: raise HTTPException(404, "Proyecto no encontrado o no vinculado a este cliente")
    project.client_id   = None
    project.client_name = None
    db.commit()
    return {"ok": True}

# ── Visión 360: resumen ejecutivo del cliente ─────────────────────────────────

@router.get("/{cid}/360")
def client_360(cid: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Vista 360 del cliente: KPIs, actividad reciente, estado de salud."""
    return svc_client_360(cid, db)
