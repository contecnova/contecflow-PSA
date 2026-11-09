"""
client_service.py — Lógica de negocio para clientes.

Funciones exportadas:
  get_client_summary(client, db) -> dict
  get_client_detail(client, db) -> dict
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


# ── Scoped query helpers ───────────────────────────────────────────────────────

def scoped_client_query(db: Session, current_user: User):
    q = db.query(Client).filter(Client.is_active == True)
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
    # Audit #C8: create Client + ClientPortalConfig must succeed atomically;
    # an orphan portal config (or worse, a client without portal config) leaks
    # into the UI and breaks tenant onboarding.
    from app.db.transactions import atomic

    if current_user.role not in ('admin', 'pm') and not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Solo admin o PM pueden crear clientes")

    with atomic(db):
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
    lic_links = db.query(ClientLicenseLink).filter(
        ClientLicenseLink.client_id == client.id,
        ClientLicenseLink.is_active == True,
    ).all()
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
    con_links = db.query(ClientContractLink).filter(
        ClientContractLink.client_id == client.id,
        ClientContractLink.is_active == True,
    ).all()
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
    portal_users = db.query(ClientUser).filter(
        ClientUser.client_org_id == client.id,
        ClientUser.is_active == True,
    ).all()
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



# ── 360 view ───────────────────────────────────────────────────────────────────

def _con_zona(dt):
    """Una fecha con zona. Las guardadas sin ella se leen como UTC."""
    return dt.replace(tzinfo=timezone.utc) if dt and dt.tzinfo is None else dt


def _valor_de_contratos(db: Session, enlaces) -> float:
    """Importe total de los contratos enlazados que tengan importe."""
    total = 0.0
    for enlace in enlaces:
        contrato = db.query(Contract).filter(Contract.id == enlace.contract_id).first()
        if contrato and contrato.total_amount:
            total += contrato.total_amount
    return total


def _licencias_por_vencer(db: Session, enlaces, ahora) -> int:
    """Licencias que vencen dentro de los próximos 60 días.

    El rango es abierto por abajo —`0 < dias`— a propósito: una licencia ya
    vencida no «vence pronto», es otro problema y otra alerta.
    """
    cuantas = 0
    for enlace in enlaces:
        licencia = db.query(ALMLicense).filter(ALMLicense.id == enlace.license_id).first()
        if not (licencia and licencia.expiry_date):
            continue
        vence = datetime.combine(licencia.expiry_date, time(0, 0)).replace(tzinfo=timezone.utc)
        if 0 < (vence - ahora).days <= 60:
            cuantas += 1
    return cuantas


#: Penalizaciones de salud del cliente: (condición sobre el resumen, puntos).
#: Auditoría 2026-09 (hallazgo 18): eran tres `if` con un `-=` cada uno. Como
#: tabla se ve la escala relativa, que es lo que hay que poder discutir.
_PENALIZACIONES_DE_SALUD: tuple[tuple, ...] = (
    (lambda r: r["abiertos"] > 5, 20),
    (lambda r: r["por_vencer"] > 0, 10),
    (lambda r: r["proyectos_activos"] == 0, 15),
)


def get_client_360(client_id: str, db: Session) -> dict:
    """Resumen ejecutivo de un cliente: KPIs, salud y alertas recientes."""
    c = db.query(Client).filter(
        Client.id == client_id, Client.is_active == True,  # noqa: E712
    ).first()
    if not c:
        raise HTTPException(404)

    ahora = datetime.now(timezone.utc)
    hace_30_dias = ahora - timedelta(days=30)

    proyectos = db.query(Project).filter(Project.client_id == client_id).all()
    activos = [p for p in proyectos if p.status == "active"]

    tickets = db.query(Ticket).filter(Ticket.client_id == client_id).all()
    abiertos = [t for t in tickets if t.status not in ("resolved", "closed")]
    recientes = [
        t for t in tickets
        if t.created_at and _con_zona(t.created_at) > hace_30_dias
    ]

    enlaces_contrato = db.query(ClientContractLink).filter(
        ClientContractLink.client_id == client_id,
        ClientContractLink.is_active == True,  # noqa: E712
    ).all()
    enlaces_licencia = db.query(ClientLicenseLink).filter(
        ClientLicenseLink.client_id == client_id,
        ClientLicenseLink.is_active == True,  # noqa: E712
    ).all()

    por_vencer = _licencias_por_vencer(db, enlaces_licencia, ahora)
    usuarios_portal = db.query(func.count(ClientUser.id)).filter(
        ClientUser.client_org_id == client_id,
        ClientUser.is_active == True,  # noqa: E712
    ).scalar() or 0

    resumen = {
        "abiertos": len(abiertos),
        "por_vencer": por_vencer,
        "proyectos_activos": len(activos),
    }
    salud = max(0, 100 - sum(
        puntos for condicion, puntos in _PENALIZACIONES_DE_SALUD if condicion(resumen)
    ))

    return {
        "client_id": client_id,
        "client_name": c.name,
        "health_score": salud,
        "kpis": {
            "total_projects": len(proyectos),
            "active_projects": len(activos),
            "total_tickets": len(tickets),
            "open_tickets": len(abiertos),
            "tickets_last_30d": len(recientes),
            "linked_contracts": len(enlaces_contrato),
            "contract_value_eur": _valor_de_contratos(db, enlaces_contrato),
            "linked_licenses": len(enlaces_licencia),
            "licenses_expiring_soon": por_vencer,
            "portal_users": usuarios_portal,
        },
        # El umbral de la alerta de tickets (3) es más bajo que el de la
        # penalización de salud (5): avisar antes de que puntúe.
        "alerts": [
            *([f"{por_vencer} licencia(s) vencen en menos de 60 días"] if por_vencer > 0 else []),
            *([f"{len(abiertos)} ticket(s) abiertos sin resolver"] if len(abiertos) > 3 else []),
        ],
        "recent_tickets": [
            {
                "id": t.id, "title": t.title, "status": t.status,
                "priority": t.priority, "created_at": str(t.created_at),
            }
            for t in sorted(tickets, key=lambda x: x.created_at or ahora, reverse=True)[:5]
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
    dependencies = []
    project_count = db.query(func.count(Project.id)).filter(Project.client_id == cid).scalar() or 0
    if project_count > 0:
        dependencies.append(f"{project_count} proyecto(s)")

    open_ticket_count = db.query(func.count(Ticket.id)).filter(
        Ticket.client_id == cid,
        Ticket.status.notin_(["resolved", "closed"]),
    ).scalar() or 0
    if open_ticket_count > 0:
        dependencies.append(f"{open_ticket_count} ticket(s) abiertos")

    invoice_count = db.query(func.count(Invoice.id)).filter(Invoice.client_id == cid).scalar() or 0
    if invoice_count > 0:
        dependencies.append(f"{invoice_count} factura(s)")

    active_contacts = db.query(func.count(ClientContact.id)).filter(
        ClientContact.client_id == cid,
        ClientContact.is_active == True,
    ).scalar() or 0
    if active_contacts > 0:
        dependencies.append(f"{active_contacts} contacto(s) activos")

    active_license_links = db.query(func.count(ClientLicenseLink.id)).filter(
        ClientLicenseLink.client_id == cid,
        ClientLicenseLink.is_active == True,
    ).scalar() or 0
    if active_license_links > 0:
        dependencies.append(f"{active_license_links} licencia(s) vinculadas")

    active_contract_links = db.query(func.count(ClientContractLink.id)).filter(
        ClientContractLink.client_id == cid,
        ClientContractLink.is_active == True,
    ).scalar() or 0
    if active_contract_links > 0:
        dependencies.append(f"{active_contract_links} contrato(s) vinculados")

    active_portal_users = db.query(func.count(ClientUser.id)).filter(
        ClientUser.client_org_id == cid,
        ClientUser.is_active == True,
    ).scalar() or 0
    if active_portal_users > 0:
        dependencies.append(f"{active_portal_users} usuario(s) de portal activos")

    if dependencies:
        raise HTTPException(400, f"No se puede eliminar: {', '.join(dependencies)}")

    c.is_active = False
    c.status = "inactive"
    db.commit()
    return {"ok": True, "message": "Cliente eliminado correctamente"}


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
    c = db.query(Client).filter(Client.id == cid, Client.is_active == True).first()
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
        ClientContact.id == contact_id,
        ClientContact.client_id == cid,
        ClientContact.is_active == True,
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
        ClientContact.id == contact_id,
        ClientContact.client_id == cid,
        ClientContact.is_active == True,
    ).first()
    if not ct:
        raise HTTPException(404)
    ct.is_active = False
    db.commit()
    return {"ok": True, "message": "Contacto eliminado correctamente"}


# ── Licenses ──────────────────────────────────────────────────────────────────

def list_client_licenses(cid: str, db: Session) -> list:
    links = db.query(ClientLicenseLink).filter(
        ClientLicenseLink.client_id == cid,
        ClientLicenseLink.is_active == True,
    ).all()
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
    if not db.query(Client).filter(Client.id == cid, Client.is_active == True).first():
        raise HTTPException(404, "Cliente no encontrado")
    lic_id = data.get("license_id")
    if not lic_id or not db.query(ALMLicense).filter(ALMLicense.id == lic_id).first():
        raise HTTPException(404, "Licencia no encontrada")
    existing = db.query(ClientLicenseLink).filter(
        ClientLicenseLink.client_id == cid,
        ClientLicenseLink.license_id == lic_id,
    ).first()
    if existing and existing.is_active:
        raise HTTPException(409, "Licencia ya vinculada a este cliente")
    if existing and not existing.is_active:
        existing.is_active = True
        existing.notes = data.get("notes")
        db.commit()
        return {"link_id": existing.id, "license_id": lic_id, "notes": existing.notes}
    ll = ClientLicenseLink(client_id=cid, license_id=lic_id, notes=data.get("notes"))
    db.add(ll)
    db.commit()
    db.refresh(ll)
    return {"link_id": ll.id, "license_id": lic_id, "notes": ll.notes}


def unlink_license(cid: str, link_id: str, db: Session) -> dict:
    ll = db.query(ClientLicenseLink).filter(
        ClientLicenseLink.id == link_id,
        ClientLicenseLink.client_id == cid,
        ClientLicenseLink.is_active == True,
    ).first()
    if not ll:
        raise HTTPException(404)
    ll.is_active = False
    db.commit()
    return {"ok": True, "message": "Licencia desvinculada correctamente"}


# ── Contracts ─────────────────────────────────────────────────────────────────

def list_client_contracts(cid: str, db: Session) -> list:
    links = db.query(ClientContractLink).filter(
        ClientContractLink.client_id == cid,
        ClientContractLink.is_active == True,
    ).all()
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
    if not db.query(Client).filter(Client.id == cid, Client.is_active == True).first():
        raise HTTPException(404, "Cliente no encontrado")
    con_id = data.get("contract_id")
    if not con_id or not db.query(Contract).filter(Contract.id == con_id).first():
        raise HTTPException(404, "Contrato no encontrado")
    existing = db.query(ClientContractLink).filter(
        ClientContractLink.client_id == cid,
        ClientContractLink.contract_id == con_id,
    ).first()
    if existing and existing.is_active:
        raise HTTPException(409, "Contrato ya vinculado")
    if existing and not existing.is_active:
        existing.is_active = True
        db.commit()
        return {"link_id": existing.id, "contract_id": con_id}
    cl = ClientContractLink(client_id=cid, contract_id=con_id)
    db.add(cl)
    db.commit()
    db.refresh(cl)
    return {"link_id": cl.id, "contract_id": con_id}


def unlink_contract(cid: str, link_id: str, db: Session) -> dict:
    cl = db.query(ClientContractLink).filter(
        ClientContractLink.id == link_id,
        ClientContractLink.client_id == cid,
        ClientContractLink.is_active == True,
    ).first()
    if not cl:
        raise HTTPException(404)
    cl.is_active = False
    db.commit()
    return {"ok": True, "message": "Contrato desvinculado correctamente"}


# ── Portal config ─────────────────────────────────────────────────────────────

def get_portal_config(cid: str, db: Session) -> dict:
    if not db.query(Client).filter(Client.id == cid, Client.is_active == True).first():
        raise HTTPException(404)
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
    if not db.query(Client).filter(Client.id == cid, Client.is_active == True).first():
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
    client = db.query(Client).filter(Client.id == cid, Client.is_active == True).first()
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
