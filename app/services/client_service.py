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
from sqlalchemy.orm import Session, joinedload

from app.services.settings_service import por_empresa as _pe
from app.models.service_desk._enums import ESTADOS_DE_TICKET_RESUELTOS
from app.core.config import settings
from app.models.user import User
from app.models.alm import ALMLicense
from app.models.billing_reports import Invoice
from app.models.client_portal import ClientUser
from app.models.clients import Client, ClientStatus
from app.models.clients import ClientPortalConfig
from app.models.clients import ClientContact, ClientContactRole, ClientLicenseLink, ClientContractLink
from app.models.pipeline import Contract
from app.models.project import Project
from app.models.service_desk import Ticket
from app.core.asignacion import campos_asignables, es_asignable
from app.core.errores import ErrorDeDominio
from app.core.paginacion import Pagina, Paginacion, paginar
from app.models.user import UserRole
from app.core.codigos_de_error import error


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
        raise error(404, "no_encontrado", detail="Cliente no encontrado", que="cliente")
    return c


def list_clients(
    db: Session,
    current_user: User,
    q: "Optional[str]" = None,
    status: "Optional[str]" = None,
    industry: "Optional[str]" = None,
    limit: "Optional[int]" = None,
    pagina: "Optional[Paginacion]" = None,
) -> Pagina:
    """``limit`` es el parametro antiguo (solo cabeza de la lista); ``pagina``, el comun."""
    query = scoped_client_query(db, current_user).options(joinedload(Client.account_manager))
    if q:
        query = query.filter(
            Client.name.ilike(f"%{q}%") |
            Client.short_name.ilike(f"%{q}%") |
            Client.contact_email.ilike(f"%{q}%") |
            Client.contact_name.ilike(f"%{q}%") |
            Client.email.ilike(f"%{q}%")
        )
    if status:
        query = query.filter(Client.status == status)
    if industry:
        query = query.filter(Client.industry == industry)
    query = query.filter(Client.is_active == True).order_by(Client.name, Client.id)
    if limit is not None and limit > 0 and (pagina is None or not pagina.pide_pagina):
        pagina = Paginacion(page=1, page_size=min(limit, settings.LIST_MAX_ROWS))
    resultado = paginar(query, pagina, "clients")
    recuentos = recuentos_de_clientes(db, [c.id for c in resultado.items])
    return resultado.mapear(lambda c: get_client_summary(c, db, recuentos[c.id]))


def recuentos_de_clientes(db: Session, ids: list) -> dict:
    """Proyectos, tickets, facturas y usuarios de portal de varios clientes.

    Segunda auditoria 2026-11 (N+1): eran cuatro ``count`` por cliente; ahora
    son cuatro ``GROUP BY`` para toda la pagina.
    """
    recuentos = {i: {"projects_count": 0, "tickets_count": 0, "invoices_count": 0, "portal_users_count": 0}
                 for i in ids}
    if not ids:
        return recuentos
    for clave, columna in (
        ("projects_count", Project.client_id),
        ("tickets_count", Ticket.client_id),
        ("invoices_count", Invoice.client_id),
        ("portal_users_count", ClientUser.client_org_id),
    ):
        for cid, n in db.query(columna, func.count()).filter(columna.in_(ids)).group_by(columna).all():
            recuentos[cid][clave] = n
    return recuentos


# ── Estado del cliente ────────────────────────────────────────────────────────
# Un cliente solo está en captación, activo, inactivo o perdido (ClientStatus).
# «Rechazado», «aprobado», «en revisión»… son estados de oportunidades,
# presupuestos, peticiones o pruebas, nunca de la empresa cliente.

def _validar_estado(data: dict) -> None:
    estado = data.get("status")
    if estado in (None, ""):
        return
    validos = [e.value for e in ClientStatus]
    if getattr(estado, "value", estado) not in validos:
        raise error(422, "estado_de_cliente_no_valido", estado=estado, opciones=', '.join(validos))


# ── Create client ──────────────────────────────────────────────────────────────

def create_client_record(data: dict, current_user: User, db: Session) -> dict:
    # Audit #C8: create Client + ClientPortalConfig must succeed atomically;
    # an orphan portal config (or worse, a client without portal config) leaks
    # into the UI and breaks tenant onboarding.
    from app.db.transactions import atomic

    if current_user.role not in (UserRole.admin, UserRole.pm) and not current_user.is_superadmin:
        raise error(403, "solo_admin_o_pm", detail="Solo admin o PM pueden crear clientes")
    _validar_estado(data)

    with atomic(db):
        c = Client(**{k: v for k, v in campos_asignables(Client, data).items() if v != "" and v is not None})
        c.created_by = current_user.id
        db.add(c)
        db.flush()
        # El contacto principal de la ficha existe también como contacto.
        sincronizar_contacto_principal(db, c)
        cfg = ClientPortalConfig(
            client_id=c.id,
            enabled_modules=json.dumps(["service_desk", "projects", "documents"]),
            sd_without_project=True,
        )
        db.add(cfg)
    db.refresh(c)
    return get_client_summary(c, db)


# ── Summary serializer ─────────────────────────────────────────────────────────

def get_client_summary(client, db: Session, recuentos: Optional[dict] = None) -> dict:

    if recuentos is None:
        recuentos = recuentos_de_clientes(db, [client.id])[client.id]
    projects_count = recuentos["projects_count"]
    tickets_count = recuentos["tickets_count"]
    invoices_count = recuentos["invoices_count"]
    portal_users_count = recuentos["portal_users_count"]

    return {
        "id": client.id, "name": client.name, "short_name": client.short_name,
        "tax_id": client.tax_id, "industry": client.industry, "status": client.status,
        # Empresa: teléfono y email generales (no los del contacto principal).
        "phone": client.phone, "email": client.email,
        # Contacto principal: reflejo del contacto `is_primary` (persona).
        "primary_contact_id": _id_del_principal(db, client.id),
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
        raise ErrorDeDominio(404)

    ahora = datetime.now(timezone.utc)
    hace_30_dias = ahora - timedelta(days=30)

    proyectos = db.query(Project).filter(Project.client_id == client_id).all()
    activos = [p for p in proyectos if p.status == "active"]

    tickets = db.query(Ticket).filter(Ticket.client_id == client_id).all()
    abiertos = [t for t in tickets if t.status not in ESTADOS_DE_TICKET_RESUELTOS]
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
    if current_user.role not in (UserRole.admin, UserRole.pm) and not current_user.is_superadmin:
        raise error(403, "solo_admin_o_pm", detail="Solo admin o PM pueden editar clientes")
    _validar_estado(data)
    c = get_scoped_client_or_404(db, current_user, cid)
    for k, v in data.items():
        if es_asignable(c, k):
            setattr(c, k, v if v != "" else None)
    if data.get("primary_contact_id"):
        # Un contacto existente pasa a ser el principal; `contact_*` lo reflejan.
        _poner_principal(db, c, data["primary_contact_id"])
    elif any(k in data for k in ("contact_name", "contact_email", "contact_phone", "contact_role")):
        sincronizar_contacto_principal(db, c)
    db.commit()
    db.refresh(c)
    return get_client_summary(c, db)


def delete_client(cid: str, current_user: User, db: Session) -> dict:
    if current_user.role not in (UserRole.admin, UserRole.pm) and not current_user.is_superadmin:
        raise error(403, "solo_admin_o_pm", detail="Solo admin o PM pueden eliminar clientes")
    c = get_scoped_client_or_404(db, current_user, cid)
    dependencies = []
    project_count = db.query(func.count(Project.id)).filter(Project.client_id == cid).scalar() or 0
    if project_count > 0:
        dependencies.append(f"{project_count} proyecto(s)")

    open_ticket_count = db.query(func.count(Ticket.id)).filter(
        Ticket.client_id == cid,
        Ticket.status.notin_(ESTADOS_DE_TICKET_RESUELTOS),
    ).scalar() or 0
    if open_ticket_count > 0:
        dependencies.append(f"{open_ticket_count} ticket(s) abiertos")

    invoice_count = db.query(func.count(Invoice.id)).filter(Invoice.client_id == cid).scalar() or 0
    if invoice_count > 0:
        dependencies.append(f"{invoice_count} factura(s)")

    # 18-11-2026: los contactos ya no impiden la baja. Son las personas del
    # cliente (todo cliente con contacto principal tiene al menos uno) y la baja
    # es lógica: siguen ahí, con el cliente, para el historial y el RGPD.

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
        raise error(400, "no_se_puede_eliminar", motivo=', '.join(dependencies))

    c.is_active = False
    c.status = "inactive"
    db.commit()
    return {"ok": True, "message": "Cliente eliminado correctamente"}


# ── Contacts ──────────────────────────────────────────────────────────────────

# ── Contacto principal ↔ contactos (18-11-2026) ─────────────────────────────
# El cliente guarda su contacto principal en `contact_*` y los contactos viven
# en `client_contacts`; antes no se relacionaban: el principal podía no existir
# como contacto, o haber dos «principales». Ahora son lo mismo visto desde dos
# sitios: el contacto marcado `is_primary` es la fuente y `contact_*` su espejo.

def _texto(v) -> str:
    return (v or "").strip()


def _buscar_contacto(db: Session, cid: str, email: str, nombre: str) -> Optional[ClientContact]:
    """Contacto activo del cliente con ese email (sin mayúsculas) o, sin email, ese nombre."""
    q = db.query(ClientContact).filter(ClientContact.client_id == cid, ClientContact.is_active == True)  # noqa: E712
    if email:
        return q.filter(func.lower(ClientContact.email) == email.lower()).first()
    if nombre:
        return q.filter(func.lower(ClientContact.full_name) == nombre.lower()).first()
    return None


def _marcar_principal(db: Session, cid: str, contacto: ClientContact) -> None:
    """Deja a `contacto` como único principal del cliente."""
    for otro in db.query(ClientContact).filter(
        ClientContact.client_id == cid,
        or_(ClientContact.is_primary == True, ClientContact.role == ClientContactRole.primary),  # noqa: E712
        ClientContact.id != contacto.id,
    ).all():
        otro.is_primary = False
        if otro.role == ClientContactRole.primary:
            otro.role = ClientContactRole.other
    contacto.is_primary = True
    contacto.role = ClientContactRole.primary


def _id_del_principal(db: Session, cid: str) -> Optional[str]:
    fila = db.query(ClientContact.id).filter(
        ClientContact.client_id == cid, ClientContact.is_active == True,  # noqa: E712
        ClientContact.is_primary == True,  # noqa: E712
    ).first()
    return fila[0] if fila else None


def _poner_principal(db: Session, cliente: Client, contact_id: str) -> ClientContact:
    """Marca un contacto activo del cliente como único principal y lo refleja en la ficha."""
    ct = db.query(ClientContact).filter(
        ClientContact.id == contact_id, ClientContact.client_id == cliente.id,
        ClientContact.is_active == True,  # noqa: E712
    ).first()
    if not ct:
        raise error(404, "no_encontrado", detail="Contacto no encontrado", que="contacto")
    _marcar_principal(db, cliente.id, ct)
    _reflejar_en_cliente(cliente, ct)
    return ct


def _reflejar_en_cliente(cliente: Client, contacto: Optional[ClientContact]) -> None:
    """Copia el contacto principal en los campos `contact_*` del cliente (o los vacía)."""
    cliente.contact_name = contacto.full_name if contacto else None
    cliente.contact_email = contacto.email if contacto else None
    cliente.contact_phone = contacto.phone if contacto else None
    cliente.contact_role = contacto.job_title if contacto else None


def sincronizar_contacto_principal(db: Session, cliente: Client) -> Optional[ClientContact]:
    """Tras crear/editar el cliente: el contacto principal escrito en la ficha
    existe como contacto (se reutiliza el que tenga ese email o nombre, o se
    crea) y es el único principal. Sin nombre ni email no hace nada."""
    nombre, email = _texto(cliente.contact_name), _texto(cliente.contact_email)
    if not nombre and not email:
        return None
    contacto = _buscar_contacto(db, cliente.id, email, nombre)
    if contacto is None:
        contacto = ClientContact(client_id=cliente.id, full_name=nombre or email,
                                 email=email or None, phone=_texto(cliente.contact_phone) or None,
                                 job_title=_texto(cliente.contact_role) or None)
        db.add(contacto)
    else:
        # Lo escrito en la ficha manda; lo vacío no borra lo que ya tenía el contacto.
        if nombre:
            contacto.full_name = nombre
        if email:
            contacto.email = email
        if _texto(cliente.contact_phone):
            contacto.phone = _texto(cliente.contact_phone)
        if _texto(cliente.contact_role):
            contacto.job_title = _texto(cliente.contact_role)
    db.flush()
    _marcar_principal(db, cliente.id, contacto)
    return contacto


# ── Usuarios del portal ↔ contactos (18-11-2026) ─────────────────────────────
# Cada usuario del portal de un cliente es una persona del cliente: existe como
# contacto suyo (`ClientContact.portal_user_id`). Desactivar el usuario no
# toca el contacto; solo deja de tener acceso.

def vincular_usuario_del_portal(db: Session, usuario: ClientUser) -> Optional[ClientContact]:
    """Tras crear o editar un usuario del portal: su contacto (el enlazado, el
    activo con su email o uno nuevo) lleva su nombre, email, teléfono y cargo.
    Sin empresa cliente no hace nada."""
    if not usuario.client_org_id:
        return None
    contacto = db.query(ClientContact).filter(ClientContact.portal_user_id == usuario.id).first()
    email = _texto(usuario.email)
    if contacto is None and email:
        contacto = db.query(ClientContact).filter(
            ClientContact.client_id == usuario.client_org_id, ClientContact.is_active == True,  # noqa: E712
            ClientContact.portal_user_id.is_(None),
            func.lower(ClientContact.email) == email.lower(),
        ).first()
    if contacto is None:
        contacto = ClientContact(client_id=usuario.client_org_id, organization_id=usuario.organization_id)
        db.add(contacto)
    contacto.portal_user_id = usuario.id
    contacto.full_name = _texto(usuario.full_name) or email or contacto.full_name
    contacto.email = email or contacto.email
    if _texto(usuario.phone):
        contacto.phone = _texto(usuario.phone)
    if _texto(usuario.job_title):
        contacto.job_title = _texto(usuario.job_title)
    db.flush()
    if contacto.is_primary:
        cliente = db.get(Client, contacto.client_id)
        if cliente is not None:
            _reflejar_en_cliente(cliente, contacto)
    return contacto


def desvincular_usuario_del_portal(db: Session, usuario_id: str) -> None:
    """Antes de borrar un usuario del portal: su contacto se queda, sin enlace."""
    for ct in db.query(ClientContact).filter(ClientContact.portal_user_id == usuario_id).all():
        ct.portal_user_id = None


def dar_acceso_al_portal(cid: str, contact_id: str, datos: dict, current_user: User, db: Session) -> dict:
    """Crea el usuario del portal de un contacto con sus datos (mismo alta, tope
    de usuarios y validaciones que la pestaña de usuarios del portal)."""
    cliente = get_scoped_client_or_404(db, current_user, cid)
    ct = db.query(ClientContact).filter(
        ClientContact.id == contact_id, ClientContact.client_id == cliente.id,
        ClientContact.is_active == True,  # noqa: E712
    ).first()
    if not ct:
        raise error(404, "no_encontrado", detail="Contacto no encontrado", que="contacto")
    if ct.portal_user_id and db.get(ClientUser, ct.portal_user_id) is not None:
        raise error(409, "contacto_ya_en_portal")
    if not _texto(ct.email):
        raise error(400, "contacto_sin_email")
    from app.schemas.client_portal import ClientCreateIn
    from app.services.client_portal_service import create_client as crear_usuario_del_portal
    payload = ClientCreateIn(
        client_org_id=cliente.id, full_name=ct.full_name, email=_texto(ct.email),
        job_title=(ct.job_title or None) and ct.job_title[:80], phone=(ct.phone or None) and ct.phone[:30],
        **{k: v for k, v in datos.items() if k in ("password", "language", "project_ids")},
    )
    try:
        creado = crear_usuario_del_portal(payload, db)
    except ValueError as e:
        from app.core.codigos_de_error import desde_valor
        raise desde_valor(400, e)
    # El enlace es con ESTE contacto (aunque otro compartiera el email).
    for otro in db.query(ClientContact).filter(ClientContact.portal_user_id == creado["id"],
                                               ClientContact.id != ct.id).all():
        otro.portal_user_id = None
    ct.portal_user_id = creado["id"]
    _auditar_contacto(db, current_user, "PORTAL_ACCESS", ct, antes={"portal_user_id": None},
                      despues={"portal_user_id": creado["id"]})
    db.commit()
    return creado


# Campos de una persona que se auditan (antes/después).
_CAMPOS_AUDITADOS = ("full_name", "email", "phone", "job_title", "role", "notes", "is_primary", "is_active",
                     "portal_user_id")


def _foto(ct: ClientContact) -> dict:
    return {k: getattr(getattr(ct, k), "value", getattr(ct, k)) for k in _CAMPOS_AUDITADOS}


def _auditar_contacto(db: Session, usuario: Optional[User], accion: str, ct: ClientContact,
                      antes: Optional[dict] = None, despues: Optional[dict] = None, **meta) -> None:
    """Auditoría de contactos (datos personales): quién, cuándo y antes/después.
    Solo los campos que cambian; el llamante confirma."""
    from app.services.audit import audit_log
    if antes is not None and despues is not None:
        cambios = [k for k in despues if antes.get(k) != despues.get(k)]
        if not cambios and not meta:
            return
        antes = {k: antes.get(k) for k in cambios}
        despues = {k: despues.get(k) for k in cambios}
    audit_log(db, usuario, accion, "client_contacts", ct.id, ct.full_name,
              old_values=antes or None, new_values=despues or None,
              metadata={"client_id": ct.client_id, **meta})


def _contacto_out(ct: ClientContact) -> dict:
    return {"id": ct.id, "full_name": ct.full_name, "email": ct.email, "phone": ct.phone,
            "job_title": ct.job_title, "role": ct.role, "notes": ct.notes,
            "is_primary": ct.is_primary}


def _contacto_activo_o_404(db: Session, cid: str, contact_id: str) -> ClientContact:
    ct = db.query(ClientContact).filter(
        ClientContact.id == contact_id, ClientContact.client_id == cid,
        ClientContact.is_active == True,  # noqa: E712
    ).first()
    if not ct:
        raise error(404, "no_encontrado", detail="Contacto no encontrado", que="contacto")
    return ct


def list_contacts(cid: str, db: Session, current_user: Optional[User] = None) -> list:
    """Contactos activos, el principal primero. Acotado a la empresa; el
    externo (subcontratado) no recibe email, teléfono ni notas
    (`politica_de_visibilidad.recortar_contacto_de_cliente`)."""
    from app.services.politica_de_visibilidad import recortar_contacto_de_cliente
    if current_user is not None:
        get_scoped_client_or_404(db, current_user, cid)
    contactos = db.query(ClientContact).filter(
        ClientContact.client_id == cid, ClientContact.is_active == True
    ).order_by(ClientContact.is_primary.desc(), ClientContact.full_name).all()
    ids = [ct.portal_user_id for ct in contactos if ct.portal_user_id]
    activos = {u.id: bool(u.is_active) for u in db.query(ClientUser).filter(ClientUser.id.in_(ids)).all()} if ids else {}
    filas = [
        {"id": ct.id, "full_name": ct.full_name, "email": ct.email,
         "phone": ct.phone, "job_title": ct.job_title, "role": ct.role,
         "is_primary": ct.is_primary, "notes": ct.notes, "is_active": ct.is_active,
         # Acceso al portal: sin usuario, `None`; con usuario, si está activo.
         "portal_user_id": ct.portal_user_id if ct.portal_user_id in activos else None,
         "portal_active": activos.get(ct.portal_user_id) if ct.portal_user_id in activos else None}
        for ct in contactos
    ]
    return [recortar_contacto_de_cliente(current_user, f) for f in filas]


def add_contact(cid: str, data: dict, db: Session, current_user: Optional[User] = None) -> dict:
    if current_user is not None:
        c = get_scoped_client_or_404(db, current_user, cid)
    else:
        c = db.query(Client).filter(Client.id == cid, Client.is_active == True).first()
        if not c:
            raise ErrorDeDominio(404)
    ct = ClientContact(client_id=cid, organization_id=c.organization_id,
                       **campos_asignables(ClientContact, data, _CONTACTO_PROTEGIDOS))
    if not _texto(ct.full_name):
        raise error(422, "nombre_vacio", detail="El nombre es obligatorio")
    db.add(ct)
    db.flush()
    # Un contacto marcado como principal pasa a ser EL principal y la ficha del cliente lo refleja.
    if ct.is_primary or ct.role == ClientContactRole.primary:
        _marcar_principal(db, cid, ct)
        _reflejar_en_cliente(c, ct)
    _auditar_contacto(db, current_user, "CREATE", ct, despues=_foto(ct))
    db.commit()
    db.refresh(ct)
    return _contacto_out(ct)


def update_contact(cid: str, contact_id: str, data: dict, db: Session,
                   current_user: Optional[User] = None) -> dict:
    if current_user is not None:
        get_scoped_client_or_404(db, current_user, cid)
    ct = _contacto_activo_o_404(db, cid, contact_id)
    antes = _foto(ct)
    era_principal = bool(ct.is_primary)
    for k, v in data.items():
        if es_asignable(ct, k, _CONTACTO_PROTEGIDOS):
            setattr(ct, k, v if v != "" or k == "full_name" else None)
    if not _texto(ct.full_name):
        raise error(422, "nombre_vacio", detail="El nombre es obligatorio")
    cliente = db.get(Client, cid)
    if ct.is_primary or (data.get("role") == ClientContactRole.primary.value):
        _marcar_principal(db, cid, ct)
        _reflejar_en_cliente(cliente, ct)
    elif era_principal:
        # Deja de ser principal: la ficha del cliente se queda sin principal.
        if ct.role == ClientContactRole.primary:
            ct.role = ClientContactRole.other
        _reflejar_en_cliente(cliente, None)
    _reflejar_en_usuario_del_portal(db, ct)
    _auditar_contacto(db, current_user, "UPDATE", ct, antes=antes, despues=_foto(ct))
    db.commit()
    db.refresh(ct)
    return _contacto_out(ct)


# El enlace con el portal y la empresa no se cambian editando el contacto.
_CONTACTO_PROTEGIDOS = ("client_id", "portal_user_id", "organization_id", "is_active", "deactivated_at")


def _reflejar_en_usuario_del_portal(db: Session, ct: ClientContact) -> None:
    """Editar un contacto con acceso al portal actualiza su usuario del portal
    (misma persona). El email es su usuario de acceso: no puede chocar con otro."""
    if not ct.portal_user_id:
        return
    usuario = db.get(ClientUser, ct.portal_user_id)
    if usuario is None:
        return
    email = _texto(ct.email)
    if email and email.lower() != _texto(usuario.email).lower():
        otro = db.query(ClientUser.id).filter(func.lower(ClientUser.email) == email.lower(),
                                              ClientUser.id != usuario.id).first()
        if otro:
            raise error(409, "email_ya_registrado", detail="Ya existe un usuario de portal con ese email")
        usuario.email = email
    if _texto(ct.full_name):
        usuario.full_name = ct.full_name
    usuario.phone = ct.phone
    usuario.job_title = (ct.job_title or None) and ct.job_title[:100]


def marcar_contacto_principal(cid: str, contact_id: str, current_user: User, db: Session) -> dict:
    """Marca un contacto como único principal del cliente y la ficha lo refleja.

    Acotado a la empresa del usuario: un cliente ajeno (o un contacto que no
    es suyo) responde 404."""
    cliente = get_scoped_client_or_404(db, current_user, cid)
    anterior = _id_del_principal(db, cliente.id)
    ct = _poner_principal(db, cliente, contact_id)
    _auditar_contacto(db, current_user, "UPDATE", ct, antes={"is_primary": anterior == ct.id},
                      despues={"is_primary": True}, previous_primary_id=anterior)
    db.commit()
    db.refresh(ct)
    return _contacto_out(ct)


def delete_contact(cid: str, contact_id: str, db: Session, current_user: Optional[User] = None) -> dict:
    """Desactiva el contacto (no se borra: el historial del cliente lo cita).
    Desde `deactivated_at` cuenta la retención (`bloqueo_legal.TIPOS`)."""
    if current_user is not None:
        get_scoped_client_or_404(db, current_user, cid)
    ct = _contacto_activo_o_404(db, cid, contact_id)
    antes = _foto(ct)
    ct.is_active = False
    ct.deactivated_at = datetime.now(timezone.utc)
    if ct.is_primary:
        ct.is_primary = False
        if ct.role == ClientContactRole.primary:
            ct.role = ClientContactRole.other
        _reflejar_en_cliente(db.get(Client, cid), None)
    _auditar_contacto(db, current_user, "DEACTIVATE", ct, antes=antes, despues=_foto(ct))
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
        raise error(404, "no_encontrado", detail="Cliente no encontrado", que="cliente")
    lic_id = data.get("license_id")
    if not lic_id or not db.query(ALMLicense).filter(ALMLicense.id == lic_id).first():
        raise error(404, "no_encontrado", detail="Licencia no encontrada", que="licencia")
    existing = db.query(ClientLicenseLink).filter(
        ClientLicenseLink.client_id == cid,
        ClientLicenseLink.license_id == lic_id,
    ).first()
    if existing and existing.is_active:
        raise error(409, "licencia_ya_vinculada")
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
        raise ErrorDeDominio(404)
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
        raise error(404, "no_encontrado", detail="Cliente no encontrado", que="cliente")
    con_id = data.get("contract_id")
    if not con_id or not db.query(Contract).filter(Contract.id == con_id).first():
        raise error(404, "no_encontrado", detail="Contrato no encontrado", que="contrato")
    existing = db.query(ClientContractLink).filter(
        ClientContractLink.client_id == cid,
        ClientContractLink.contract_id == con_id,
    ).first()
    if existing and existing.is_active:
        raise error(409, "contrato_ya_vinculado")
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
        raise ErrorDeDominio(404)
    cl.is_active = False
    db.commit()
    return {"ok": True, "message": "Contrato desvinculado correctamente"}


# ── Portal config ─────────────────────────────────────────────────────────────

def get_portal_config(cid: str, db: Session) -> dict:
    if not db.query(Client).filter(Client.id == cid, Client.is_active == True).first():
        raise ErrorDeDominio(404)
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
        "default_language": cfg.default_language or _pe.idioma_de_empresa(db, registro=cfg),  # 18-11-2026
        "allow_profile_edit": cfg.allow_profile_edit if cfg.allow_profile_edit is not None else True,
        "allow_pwd_change": cfg.allow_pwd_change if cfg.allow_pwd_change is not None else True,
    }


def update_portal_config(cid: str, data: dict, db: Session) -> dict:
    if not db.query(Client).filter(Client.id == cid, Client.is_active == True).first():
        raise ErrorDeDominio(404)
    cfg = db.query(ClientPortalConfig).filter(ClientPortalConfig.client_id == cid).first()
    if not cfg:
        cfg = ClientPortalConfig(client_id=cid)
        db.add(cfg)
    for k, v in data.items():
        if k == "enabled_modules":
            setattr(cfg, k, json.dumps(v))
        elif es_asignable(cfg, k, ("client_id",)):
            setattr(cfg, k, v)
    db.commit()
    db.refresh(cfg)
    return {"ok": True, "enabled_modules": json.loads(cfg.enabled_modules)}


# ── Invoices ──────────────────────────────────────────────────────────────────

def list_client_invoices(cid: str, db: Session, pagina: Optional[Paginacion] = None) -> Pagina:
    """Facturas del cliente: las suyas y las de sus proyectos, en una consulta.

    Segunda auditoria 2026-11: eran tres consultas y la union en Python (sin
    tope), mas el proyecto de cada factura por separado (N+1); y leia
    ``inv.total_amount``, que ``Invoice`` no tiene —la ruta daba 500 en cuanto
    el cliente tenia una factura—. El importe es ``Invoice.total``; la clave de
    la respuesta sigue siendo ``total_amount``.
    """
    proyectos = db.query(Project.id).filter(Project.client_id == cid)
    q = (
        db.query(Invoice)
        .options(joinedload(Invoice.project))
        .filter(or_(Invoice.client_id == cid, Invoice.project_id.in_(proyectos)))
        .order_by(Invoice.issue_date.desc().nullslast(), Invoice.id)
    )
    return paginar(q, pagina, "clients.invoices").mapear(lambda inv: {
        "id": inv.id,
        "number": inv.number,
        "status": inv.status,
        "issue_date": str(inv.issue_date) if inv.issue_date else None,
        "due_date": str(inv.due_date) if inv.due_date else None,
        "total_amount": inv.total,
        "project_id": inv.project_id,
        "project_name": inv.project.name if inv.project else None,
        "client_name": inv.client_name,
    })


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

def _estado(status) -> str:
    """Valor plano del enum. Auditoria 2026-11: `str(ProjectStatus.active)` da
    "ProjectStatus.active" (enum con mezcla de str) y asi llegaba a la interfaz."""
    return getattr(status, "value", status) or ""


def list_client_projects(cid: str, db: Session) -> list:
    projects = db.query(Project).filter(Project.client_id == cid).order_by(Project.name).all()
    return [
        {"id": p.id, "code": p.code, "name": p.name, "status": _estado(p.status),
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
        status_val = _estado(getattr(p, "status", ""))
        if status_val == "cancelled":
            continue
        if not cid_val or cid_val == "" or cid_val == cid:
            projects.append(p)
    return [
        {
            "id": p.id,
            "code": getattr(p, "code", ""),
            "name": p.name,
            "status": _estado(p.status),
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
        raise error(404, "no_encontrado", detail="Cliente no encontrado", que="cliente")
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise error(404, "no_encontrado", detail="Proyecto no encontrado", que="proyecto")
    if project.client_id and project.client_id != cid:
        other = db.query(Client).filter(Client.id == project.client_id).first()
        raise error(409, "proyecto_ya_vinculado_a_cliente", detail=f"El proyecto ya está vinculado al cliente '{other.name if other else project.client_id}'", cliente=other.name if other else project.client_id)
    project.client_id = cid
    project.client_name = client.name
    db.commit()
    return {"ok": True, "project_id": project_id, "client_id": cid}


def unlink_project(cid: str, project_id: str, db: Session) -> dict:
    project = db.query(Project).filter(
        Project.id == project_id, Project.client_id == cid
    ).first()
    if not project:
        raise error(404, "proyecto_no_vinculado_a_cliente")
    project.client_id = None
    project.client_name = None
    db.commit()
    return {"ok": True}
