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


# ── Scoped query helpers ───────────────────────────────────────────────────────

def scoped_client_query(db: Session, current_user: User):
    from app.models.clients import Client
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
    from fastapi import HTTPException
    c = scoped_client_query(db, current_user).filter_by(id=client_id).first()
    if not c:
        raise HTTPException(404, "Cliente no encontrado")
    return c


# ── Create client ──────────────────────────────────────────────────────────────

def create_client_record(data: dict, current_user: User, db: Session) -> dict:
    from fastapi import HTTPException
    from app.models.clients import Client, ClientPortalConfig

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
    from app.models.project import Project
    from app.models.service_desk import Ticket
    from app.models.client_portal import ClientUser
    from app.models.billing_reports import Invoice

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
    from app.models.project import Project
    from app.models.pipeline import Contract
    from app.models.alm import ALMLicense
    from app.models.service_desk import Ticket
    from app.models.client_portal import ClientUser
    from app.models.clients import ClientContact, ClientPortalConfig, ClientLicenseLink, ClientContractLink

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
    from fastapi import HTTPException
    from sqlalchemy.exc import IntegrityError
    from app.models.clients import ClientPortalConfig
    from app.models.client_portal import ClientUser

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
    from app.models.clients import Client
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
    from fastapi import HTTPException
    from app.models.clients import Client, ClientLicenseLink, ClientContractLink
    from app.models.project import Project
    from app.models.service_desk import Ticket
    from app.models.client_portal import ClientUser
    from app.models.pipeline import Contract
    from app.models.alm import ALMLicense

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
