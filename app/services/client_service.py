"""
client_service.py — Lógica de negocio para clientes.

Funciones exportadas:
  get_client_summary(client, db) -> dict
  get_client_detail(client, db) -> dict
  create_portal_user(client_id, data, current_user, db) -> dict
  get_client_360(client_id, db) -> dict
  scoped_client_query(db, current_user) -> Query
  get_scoped_client_or_404(db, current_user, client_id) -> Client
  create_client_record(data, current_user, db) -> dict
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone, time
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import User
from app.models.alm import ALMLicense
from app.models.billing_reports import Invoice
from app.models.client_portal import ClientUser
from app.models.clients import Client
from app.models.clients import ClientPortalConfig
from app.models.clients import ClientContact, ClientLicenseLink, ClientContractLink
from app.models.pipeline import Contract
from app.models.project import Project
from app.models.service_desk import Ticket
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError


# ── Scoped query helpers ───────────────────────────────────────────────────────

def scoped_client_query(db: Session, current_user: User):
    q = db.query(Client)
    if current_user.is_superadmin or not current_user.organization_id:
        return q
    org_user_ids = db.query(User.id).filter(
        User.organization_id == current_user.organization_id
    ).scalar_subquery()
    return q.filter(
        or_(
            Client.created_by.in_(org_user_ids),
            Client.account_manager_id.in_(org_user_ids),
        )
    )


def get_scoped_client_or_404(db: Session, current_user: User, client_id: str):
    c = scoped_client_query(db, current_user).filter_by(id=client_id).first()
    if not c:
        raise HTTPException(404, "Cliente no encontrado")
    return c


def list_clients(
    db: Session,
    current_user: User,
    q: "Optional[str]" = None,
    status: "Optional[str]" = None,
    industry: "Optional[str]" = None,
    limit: "Optional[int]" = None,
) -> list:
    query = scoped_client_query(db, current_user)
    if q:
        query = query.filter(
            Client.name.ilike(f"%{q}%") |
            Client.short_name.ilike(f"%{q}%") |
            Client.contact_email.ilike(f"%{q}%")
        )
    if status:
        query = query.filter(Client.status == status)
    if industry:
        query = query.filter(Client.industry == industry)
    query = query.filter(Client.is_active == True).order_by(Client.name)
    if limit is not None and limit > 0:
        query = query.limit(limit)
    return [get_client_summary(c, db) for c in query.all()]


# ── Create client ──────────────────────────────────────────────────────────────

def create_client_record(data: dict, current_user: User, db: Session) -> dict:

    if current_user.role not in ('admin', 'pm') and not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Solo admin o PM pueden crear clientes")

    c = Client(**{k: v for k, v in data.items() if hasattr(Client, k) and v != "" and v is not None})
    c.created_by = current_user.id
    db.add(c)
    db.flush()
    cfg = ClientPortalConfig(
        client_id=c.id,
        enabled_modules=json.dumps(["service_desk", "projects", "documents"]),
        sd_without_project=True,
    )
    db.add(cfg)
    db.commit()
    db.refresh(c)
    return get_client_summary(c, db)


# ── Summary serializer ─────────────────────────────────────────────────────────

def get_client_summary(client, db: Session) -> dict:

    projects_count = db.query(func.count(Project.id)).filter(Project.client_id == client.id).scalar() or 0
    tickets_count = db.query(func.count(Ticket.id)).filter(Ticket.client_id == client.id).scalar() or 0
    invoices_count = db.query(func.count(Invoice.id)).filter(Invoice.client_id == client.id).scalar() or 0
    portal_users_count = db.query(func.count(ClientUser.id)).filter(ClientUser.client_org_id == client.id).scalar() or 0

    return {
        "id": client.id, "name": client.name, "short_name": client.short_name,
        "tax_id": client.tax_id, "industry": client.industry, "status": client.status,
        "contact_name": client.contact_name, "contact_email": client.contact_email,
        "contact_phone": client.contact_phone, "contact_role": client.contact_role,
        "website": client.website, "address": client.address,
        "city": client.city, "country": client.country,
        "account_manager_id": client.account_manager_id,
        "account_manager_name": client.account_manager.full_name if client.account_manager else None,
        "payment_terms": client.payment_terms, "credit_limit": client.credit_limit,
        "currency": client.currency, "notes": client.notes, "is_active": client.is_active,
        "projects_count": projects_count,
        "tickets_count": tickets_count,
        "invoices_count": invoices_count,
        "portal_users_count": portal_users_count,
        "created_at": str(client.created_at),
    }


# ── Detail serializer ──────────────────────────────────────────────────────────

def get_client_detail(client, db: Session) -> dict:
    """Full client detail with all related entities (360 queries batched)."""

    out = get_client_summary(client, db)

    # Projects
    out["projects"] = [
        {
            "id": p.id, "code": p.code, "name": p.name, "status": p.status,
            "start_date": str(p.start_date) if getattr(p, "start_date", None) else None,
            "end_date": str(getattr(p, "end_date_planned", None) or getattr(p, "end_date", None))
                if (getattr(p, "end_date_planned", None) or getattr(p, "end_date", None)) else None,
        }
        for p in db.query(Project).filter(Project.client_id == client.id).order_by(Project.name).all()
    ]

    # Contacts
    out["contacts"] = [
        {
            "id": ct.id, "full_name": ct.full_name, "email": ct.email,
            "phone": ct.phone, "job_title": ct.job_title, "role": ct.role,
            "is_primary": ct.is_primary,
        }
        for ct in db.query(ClientContact).filter(
            ClientContact.client_id == client.id, ClientContact.is_active == True
        ).order_by(ClientContact.is_primary.desc()).all()
    ]

    # Licenses
    lic_links = db.query(ClientLicenseLink).filter(ClientLicenseLink.client_id == client.id).all()
    licenses = []
    for ll in lic_links:
        lic = db.query(ALMLicense).filter(ALMLicense.id == ll.license_id).first()
        if lic:
            licenses.append({
                "link_id": ll.id, "license_id": lic.id, "name": lic.name,
                "vendor": getattr(lic, "vendor_name", None),
                "status": lic.status,
                "expiry_date": str(lic.expiry_date) if lic.expiry_date else None,
                "total_seats": lic.total_seats, "notes": ll.notes,
            })
    out["licenses"] = licenses

    # Contracts
    con_links = db.query(ClientContractLink).filter(ClientContractLink.client_id == client.id).all()
    contracts_list = []
    for cl in con_links:
        con = db.query(Contract).filter(Contract.id == cl.contract_id).first()
        if con:
            contracts_list.append({
                "link_id": cl.id, "contract_id": con.id,
                "reference": getattr(con, "reference", None),
                "title": getattr(con, "title", None) or con.client_name,
                "status": con.status, "total_amount": con.total_amount,
                "start_date": str(con.start_date) if con.start_date else None,
                "end_date": str(con.end_date) if con.end_date else None,
            })
    out["contracts"] = contracts_list

    # Tickets (recent 20)
    tickets = db.query(Ticket).filter(Ticket.client_id == client.id).order_by(
        Ticket.created_at.desc()
    ).limit(20).all()
    out["tickets"] = [
        {
            "id": t.id, "code": getattr(t, "code", t.id[:8]),
            "title": t.title, "status": t.status, "priority": t.priority,
            "created_at": str(t.created_at),
        }
        for t in tickets
    ]

    # Portal users
    portal_users = db.query(ClientUser).filter(ClientUser.client_org_id == client.id).all()
    out["portal_users"] = [
        {
            "id": u.id, "full_name": u.full_name, "email": u.email,
            "job_title": u.job_title, "is_active": u.is_active,
            "project_id": u.project_id,
            "last_login": str(u.last_login) if u.last_login else None,
        }
        for u in portal_users
    ]

    # Portal config
    cfg = db.query(ClientPortalConfig).filter(ClientPortalConfig.client_id == client.id).first()
    out["portal_config"] = _portal_config_out(cfg)

    return out


def _portal_config_out(cfg) -> dict:
    if cfg:
        return {
            "enabled_modules": json.loads(cfg.enabled_modules) if cfg.enabled_modules else [],
            "sd_without_project": cfg.sd_without_project,
            "sla_tier": cfg.sla_tier,
            "max_portal_users": cfg.max_portal_users,
            "max_open_tickets": cfg.max_open_tickets,
        }
    return {
        "enabled_modules": ["service_desk", "projects", "documents"],
        "sd_without_project": True,
        "sla_tier": None,
        "max_portal_users": 10,
        "max_open_tickets": None,
    }


# ── Portal user creation ───────────────────────────────────────────────────────

def create_portal_user(
    client_id: str,
    data: dict,
    current_user: User,
    db: Session,
) -> dict:
    """
    Create a portal user for a client, enforcing max_portal_users limit and email uniqueness.
    Returns {"id", "full_name", "email", "temp_password"} dict.
    """
    import secrets
    import bcrypt

    cfg = db.query(ClientPortalConfig).filter(ClientPortalConfig.client_id == client_id).first()

    if cfg and cfg.max_portal_users:
        current_count = db.query(func.count(ClientUser.id)).filter(
            ClientUser.client_org_id == client_id, ClientUser.is_active == True
        ).scalar() or 0
        if current_count >= cfg.max_portal_users:
            raise HTTPException(400, f"Límite de usuarios de portal alcanzado ({cfg.max_portal_users})")

    if db.query(ClientUser).filter(ClientUser.email == data.get("email")).first():
        raise HTTPException(409, "Email ya registrado en el portal")

    provided_pwd = data.pop("password", None)
    pwd = provided_pwd or secrets.token_urlsafe(12)
    hashed = bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode()

    # Look up client name for company field
    client = db.query(Client).filter(Client.id == client_id).first()

    u = ClientUser(
        client_org_id=client_id,
        project_id=data.get("project_id"),
        full_name=data.get("full_name", ""),
        email=data.get("email", ""),
        job_title=data.get("job_title"),
        phone=data.get("phone"),
        company=client.name if client else "",
        hashed_password=hashed,
        can_approve_deliverables=data.get("can_approve_deliverables", True),
        can_request_changes=data.get("can_request_changes", True),
        can_view_budget=data.get("can_view_budget", False),
        can_view_team=data.get("can_view_team", False),
        language=data.get("language", settings.DEFAULT_LANGUAGE),
    )
    try:
        db.add(u)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Email ya registrado en el portal")
    db.refresh(u)
    return {
        "id": u.id,
        "full_name": u.full_name,
        "email": u.email,
        "temp_password": pwd if not provided_pwd else None,
    }


# ── 360 view ───────────────────────────────────────────────────────────────────

def get_client_360(client_id: str, db: Session) -> dict:
    """Executive 360 summary: KPIs, health score, recent alerts."""

    c = db.query(Client).filter(Client.id == client_id).first()
    if not c:
        raise HTTPException(404)

    now = datetime.now(timezone.utc)
    thirty_days_ago = now - timedelta(days=30)

    all_projects = db.query(Project).filter(Project.client_id == client_id).all()
    active_projects = [p for p in all_projects if p.status == "active"]

    all_tickets = db.query(Ticket).filter(Ticket.client_id == client_id).all()
    open_tickets = [t for t in all_tickets if t.status not in ("resolved", "closed")]

    def _to_aware(dt):
        return dt.replace(tzinfo=timezone.utc) if dt and dt.tzinfo is None else dt

    recent_tickets = [
        t for t in all_tickets
        if t.created_at and _to_aware(t.created_at) > thirty_days_ago
    ]

    con_links = db.query(ClientContractLink).filter(ClientContractLink.client_id == client_id).all()
    contract_value = 0
    for cl in con_links:
        con = db.query(Contract).filter(Contract.id == cl.contract_id).first()
        if con and con.total_amount:
            contract_value += con.total_amount

    lic_links = db.query(ClientLicenseLink).filter(ClientLicenseLink.client_id == client_id).all()
    expiring_soon = 0
    for ll in lic_links:
        lic = db.query(ALMLicense).filter(ALMLicense.id == ll.license_id).first()
        if lic and lic.expiry_date:
            exp = datetime.combine(lic.expiry_date, time(0, 0)).replace(tzinfo=timezone.utc)
            if 0 < (exp - now).days <= 60:
                expiring_soon += 1

    portal_users_count = db.query(func.count(ClientUser.id)).filter(
        ClientUser.client_org_id == client_id, ClientUser.is_active == True
    ).scalar() or 0

    health = 100
    if len(open_tickets) > 5:
        health -= 20
    if expiring_soon > 0:
        health -= 10
    if not active_projects:
        health -= 15
    health = max(0, health)

    return {
        "client_id": client_id,
        "client_name": c.name,
        "health_score": health,
        "kpis": {
            "total_projects": len(all_projects),
            "active_projects": len(active_projects),
            "total_tickets": len(all_tickets),
            "open_tickets": len(open_tickets),
            "tickets_last_30d": len(recent_tickets),
            "linked_contracts": len(con_links),
            "contract_value_eur": contract_value,
            "linked_licenses": len(lic_links),
            "licenses_expiring_soon": expiring_soon,
            "portal_users": portal_users_count,
        },
        "alerts": [
            *([f"{expiring_soon} licencia(s) vencen en menos de 60 días"] if expiring_soon > 0 else []),
            *([f"{len(open_tickets)} ticket(s) abiertos sin resolver"] if len(open_tickets) > 3 else []),
        ],
        "recent_tickets": [
            {
                "id": t.id, "title": t.title, "status": t.status,
                "priority": t.priority, "created_at": str(t.created_at),
            }
            for t in sorted(all_tickets, key=lambda x: x.created_at or now, reverse=True)[:5]
        ],
    }


# ── Client CRUD ───────────────────────────────────────────────────────────────

def update_client(cid: str, data: dict, current_user: User, db: Session) -> dict:
    if current_user.role not in ('admin', 'pm') and not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Solo admin o PM pueden editar clientes")
    c = get_scoped_client_or_404(db, current_user, cid)
    for k, v in data.items():
        if hasattr(c, k):
            setattr(c, k, v if v != "" else None)
    db.commit()
    db.refresh(c)
    return get_client_summary(c, db)


def delete_client(cid: str, current_user: User, db: Session) -> dict:
    if current_user.role not in ('admin', 'pm') and not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Solo admin o PM pueden eliminar clientes")
    c = get_scoped_client_or_404(db, current_user, cid)
    db.query(Project).filter(Project.client_id == cid).update({"client_id": None})
    c.is_active = False
    db.commit()
    return {"ok": True}


# ── Contacts ──────────────────────────────────────────────────────────────────

def list_contacts(cid: str, db: Session) -> list:
    return [
        {"id": ct.id, "full_name": ct.full_name, "email": ct.email,
         "phone": ct.phone, "job_title": ct.job_title, "role": ct.role,
         "is_primary": ct.is_primary, "notes": ct.notes, "is_active": ct.is_active}
        for ct in db.query(ClientContact).filter(
            ClientContact.client_id == cid, ClientContact.is_active == True
        ).order_by(ClientContact.is_primary.desc()).all()
    ]


def add_contact(cid: str, data: dict, db: Session) -> dict:
    c = db.query(Client).filter(Client.id == cid).first()
    if not c:
        raise HTTPException(404)
    ct = ClientContact(client_id=cid, **{k: v for k, v in data.items() if hasattr(ClientContact, k)})
    db.add(ct)
    db.commit()
    db.refresh(ct)
    return {"id": ct.id, "full_name": ct.full_name, "email": ct.email,
            "phone": ct.phone, "job_title": ct.job_title, "role": ct.role,
            "is_primary": ct.is_primary}


def update_contact(cid: str, contact_id: str, data: dict, db: Session) -> dict:
    ct = db.query(ClientContact).filter(
        ClientContact.id == contact_id, ClientContact.client_id == cid
    ).first()
    if not ct:
        raise HTTPException(404)
    for k, v in data.items():
        if hasattr(ct, k):
            setattr(ct, k, v)
    db.commit()
    db.refresh(ct)
    return {"id": ct.id, "full_name": ct.full_name, "email": ct.email, "role": ct.role}


def delete_contact(cid: str, contact_id: str, db: Session) -> dict:
    ct = db.query(ClientContact).filter(
        ClientContact.id == contact_id, ClientContact.client_id == cid
    ).first()
    if not ct:
        raise HTTPException(404)
    ct.is_active = False
    db.commit()
    return {"ok": True}


# ── Licenses ──────────────────────────────────────────────────────────────────

def list_client_licenses(cid: str, db: Session) -> list:
    links = db.query(ClientLicenseLink).filter(ClientLicenseLink.client_id == cid).all()
    result = []
    for ll in links:
        lic = db.query(ALMLicense).filter(ALMLicense.id == ll.license_id).first()
        if lic:
            result.append({
                "link_id": ll.id, "license_id": lic.id, "name": lic.name,
                "status": lic.status,
                "expiry_date": str(lic.expiry_date) if lic.expiry_date else None,
                "total_seats": lic.total_seats, "annual_cost": lic.annual_cost,
                "notes": ll.notes, "linked_at": str(ll.linked_at),
            })
    return result


def link_license(cid: str, data: dict, db: Session) -> dict:
    if not db.query(Client).filter(Client.id == cid).first():
        raise HTTPException(404, "Cliente no encontrado")
    lic_id = data.get("license_id")
    if not lic_id or not db.query(ALMLicense).filter(ALMLicense.id == lic_id).first():
        raise HTTPException(404, "Licencia no encontrada")
    existing = db.query(ClientLicenseLink).filter(
        ClientLicenseLink.client_id == cid, ClientLicenseLink.license_id == lic_id
    ).first()
    if existing:
        raise HTTPException(409, "Licencia ya vinculada a este cliente")
    ll = ClientLicenseLink(client_id=cid, license_id=lic_id, notes=data.get("notes"))
    db.add(ll)
    db.commit()
    db.refresh(ll)
    return {"link_id": ll.id, "license_id": lic_id, "notes": ll.notes}


def unlink_license(cid: str, link_id: str, db: Session) -> dict:
    ll = db.query(ClientLicenseLink).filter(
        ClientLicenseLink.id == link_id, ClientLicenseLink.client_id == cid
    ).first()
    if not ll:
        raise HTTPException(404)
    db.delete(ll)
    db.commit()
    return {"ok": True}


# ── Contracts ─────────────────────────────────────────────────────────────────

def list_client_contracts(cid: str, db: Session) -> list:
    links = db.query(ClientContractLink).filter(ClientContractLink.client_id == cid).all()
    linked_ids: set = set()
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
    direct = db.query(Contract).filter(
        Contract.client_id == cid, Contract.id.notin_(linked_ids)
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


def link_contract(cid: str, data: dict, db: Session) -> dict:
    if not db.query(Client).filter(Client.id == cid).first():
        raise HTTPException(404, "Cliente no encontrado")
    con_id = data.get("contract_id")
    if not con_id or not db.query(Contract).filter(Contract.id == con_id).first():
        raise HTTPException(404, "Contrato no encontrado")
    existing = db.query(ClientContractLink).filter(
        ClientContractLink.client_id == cid, ClientContractLink.contract_id == con_id
    ).first()
    if existing:
        raise HTTPException(409, "Contrato ya vinculado")
    cl = ClientContractLink(client_id=cid, contract_id=con_id)
    db.add(cl)
    db.commit()
    db.refresh(cl)
    return {"link_id": cl.id, "contract_id": con_id}


def unlink_contract(cid: str, link_id: str, db: Session) -> dict:
    cl = db.query(ClientContractLink).filter(
        ClientContractLink.id == link_id, ClientContractLink.client_id == cid
    ).first()
    if not cl:
        raise HTTPException(404)
    db.delete(cl)
    db.commit()
    return {"ok": True}


# ── Portal config ─────────────────────────────────────────────────────────────

def get_portal_config(cid: str, db: Session) -> dict:
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


def update_portal_config(cid: str, data: dict, db: Session) -> dict:
    if not db.query(Client).filter(Client.id == cid).first():
        raise HTTPException(404)
    cfg = db.query(ClientPortalConfig).filter(ClientPortalConfig.client_id == cid).first()
    if not cfg:
        cfg = ClientPortalConfig(client_id=cid)
        db.add(cfg)
    for k, v in data.items():
        if k == "enabled_modules":
            setattr(cfg, k, json.dumps(v))
        elif hasattr(cfg, k) and k not in ("client_id", "id", "created_at", "updated_at"):
            setattr(cfg, k, v)
    db.commit()
    db.refresh(cfg)
    return {"ok": True, "enabled_modules": json.loads(cfg.enabled_modules)}


# ── Invoices ──────────────────────────────────────────────────────────────────

def list_client_invoices(cid: str, db: Session) -> list:
    direct = db.query(Invoice).filter(Invoice.client_id == cid).all()
    seen_ids = {inv.id for inv in direct}
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


# ── Tickets ───────────────────────────────────────────────────────────────────

def list_client_tickets(cid: str, status: "Optional[str]", db: Session) -> list:
    q = db.query(Ticket).filter(Ticket.client_id == cid)
    if status:
        q = q.filter(Ticket.status == status)
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


# ── Portal users ──────────────────────────────────────────────────────────────

def list_portal_users(cid: str, db: Session) -> list:
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


def update_portal_user(cid: str, uid: str, data: dict, db: Session) -> dict:
    u = db.query(ClientUser).filter(
        ClientUser.id == uid, ClientUser.client_org_id == cid
    ).first()
    if not u:
        raise HTTPException(404)
    for k, v in data.items():
        if hasattr(u, k) and k not in ('id', 'hashed_password', 'client_org_id'):
            setattr(u, k, v)
    db.commit()
    return {"id": u.id, "full_name": u.full_name, "email": u.email, "is_active": u.is_active}


# ── Client-project linking ────────────────────────────────────────────────────

def list_client_projects(cid: str, db: Session) -> list:
    projects = db.query(Project).filter(Project.client_id == cid).order_by(Project.name).all()
    return [
        {"id": p.id, "code": p.code, "name": p.name, "status": str(p.status),
         "client_id": p.client_id, "is_linked": True,
         "start_date": str(getattr(p, "start_date", None)) if getattr(p, "start_date", None) else None,
         "end_date": str(getattr(p, "end_date_planned", None) or getattr(p, "end_date", None))
             if (getattr(p, "end_date_planned", None) or getattr(p, "end_date", None)) else None}
        for p in projects
    ]


def list_available_projects(cid: str, db: Session) -> list:
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
            "end_date": str(getattr(p, "end_date_planned", None) or getattr(p, "end_date", None))
                if (getattr(p, "end_date_planned", None) or getattr(p, "end_date", None)) else None,
        }
        for p in projects
    ]


def link_project(cid: str, project_id: str, db: Session) -> dict:
    client = db.query(Client).filter(Client.id == cid).first()
    if not client:
        raise HTTPException(404, "Cliente no encontrado")
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Proyecto no encontrado")
    if project.client_id and project.client_id != cid:
        other = db.query(Client).filter(Client.id == project.client_id).first()
        raise HTTPException(409, f"El proyecto ya está vinculado al cliente '{other.name if other else project.client_id}'")
    project.client_id = cid
    project.client_name = client.name
    db.commit()
    return {"ok": True, "project_id": project_id, "client_id": cid}


def unlink_project(cid: str, project_id: str, db: Session) -> dict:
    project = db.query(Project).filter(
        Project.id == project_id, Project.client_id == cid
    ).first()
    if not project:
        raise HTTPException(404, "Proyecto no encontrado o no vinculado a este cliente")
    project.client_id = None
    project.client_name = None
    db.commit()
    return {"ok": True}
