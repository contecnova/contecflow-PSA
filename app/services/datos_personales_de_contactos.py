"""RGPD de las personas de un cliente: contactos y usuarios del portal (18-11-2026).

Un contacto de cliente (`ClientContact`) y un usuario del portal (`ClientUser`)
son datos personales de alguien que no es usuario de la aplicación: se le
identifica por su **email**. Las solicitudes RGPD (`cab_service/gdpr.py`) los
incluyen así:

- **Acceso y portabilidad**: la copia lleva sus fichas de contacto (de todos los
  clientes de la empresa) y, si la tiene, su cuenta del portal.
- **Supresión**: se anonimizan (nombre «[ERASED]», email, teléfono, cargo y
  notas vacíos; desactivados). El `id` se queda: el historial del cliente y sus
  referencias siguen cuadrando, ya sin nadie identificable. Si era el contacto
  principal, la ficha del cliente deja de reflejarlo. La cuenta del portal se
  anonimiza igual, sin contraseña.
- **Bloqueo legal**: un bloqueo activo del tipo `client_contacts` (o `*`) cuyo
  valor es el id, el email o el cliente del contacto impide la supresión (409),
  antes de tocar nada.

`audit_logs` no se reescribe (RGPD art. 17.3.b/e), como en `supresion_service`.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.client_portal import ClientUser
from app.models.clients import Client, ClientContact, ClientContactRole
from app.services.supresion_service import BORRADO, _seudonimo


def _email(v) -> str:
    return (v or "").strip().lower()


def contactos_de(db: Session, email: str, org: Optional[str]) -> list:
    """Fichas de contacto (activas o no) con ese email en clientes de la empresa."""
    if not _email(email):
        return []
    q = db.query(ClientContact).join(Client, Client.id == ClientContact.client_id).filter(
        func.lower(ClientContact.email) == _email(email))
    if org:
        q = q.filter(Client.organization_id == org)
    return q.order_by(ClientContact.created_at, ClientContact.id).all()


def usuarios_del_portal_de(db: Session, email: str, org: Optional[str]) -> list:
    if not _email(email):
        return []
    q = db.query(ClientUser).filter(func.lower(ClientUser.email) == _email(email))
    if org:
        q = q.filter(ClientUser.organization_id == org)
    return q.all()


def copia(db: Session, email: str, org: Optional[str]) -> dict:
    """Sus datos como contacto de cliente y como usuario del portal (art. 15 y 20)."""
    contactos = contactos_de(db, email, org)
    clientes = {c.id: c.name for c in db.query(Client).filter(
        Client.id.in_({ct.client_id for ct in contactos}))} if contactos else {}
    return {
        "client_contacts": [{
            "client": clientes.get(ct.client_id), "full_name": ct.full_name, "email": ct.email,
            "phone": ct.phone, "job_title": ct.job_title, "role": getattr(ct.role, "value", ct.role),
            "is_primary": bool(ct.is_primary), "notes": ct.notes, "is_active": bool(ct.is_active),
            "created_at": str(ct.created_at)[:19] if ct.created_at else None,
        } for ct in contactos],
        "portal_users": [{
            "full_name": u.full_name, "email": u.email, "phone": u.phone, "job_title": u.job_title,
            "company": u.company, "language": u.language, "is_active": bool(u.is_active),
            "last_login": str(u.last_login)[:19] if u.last_login else None,
            "created_at": str(u.created_at)[:19] if u.created_at else None,
        } for u in usuarios_del_portal_de(db, email, org)],
    }


def bloqueos(db: Session, email: str, org: Optional[str]) -> list:
    """Bloqueos legales activos que cubren alguno de sus contactos."""
    from app.db.bloqueo_legal import _bloqueo_de, bloqueos_activos
    contactos = contactos_de(db, email, org)
    if not contactos:
        return []
    activos = bloqueos_activos(db, org)
    vistos = [_bloqueo_de("client_contacts", ct, activos) for ct in contactos]
    return [b for b in vistos if b is not None]


def exigir_sin_bloqueo_legal(db: Session, email: str, org: Optional[str]) -> None:
    from app.core.errores import ErrorDeDominio
    casos = sorted({b.case_reference for b in bloqueos(db, email, org)})
    if casos:
        from app.core.codigos_de_error import error
        raise error(409, "bloqueo_legal_no_suprimible", casos=", ".join(casos),
                    detail="El contacto está bajo bloqueo legal y no se puede suprimir: " + ", ".join(casos))


def anonimizar(db: Session, email: str, org: Optional[str]) -> dict:
    """Supresión de sus fichas de contacto y su cuenta del portal. No hace commit.
    Bajo bloqueo legal lanza 409 sin tocar nada."""
    from app.services.client_service import _reflejar_en_cliente
    # M81 (auditoría 22-11-2026): sin empresa no se suprime (antes, con `org=None`,
    # se anonimizaban las fichas con ese correo en TODAS las empresas).
    if not org:
        from app.core.codigos_de_error import error
        raise error(422, "campo_obligatorio", campo="organization_id")
    exigir_sin_bloqueo_legal(db, email, org)
    contactos = contactos_de(db, email, org)
    usuarios = usuarios_del_portal_de(db, email, org)
    ahora = datetime.now(timezone.utc)
    for ct in contactos:
        if ct.is_primary:
            # La ficha deja de reflejar a esa persona.
            cliente = db.get(Client, ct.client_id)
            if cliente is not None:
                _reflejar_en_cliente(cliente, None)
            ct.is_primary = False
        if ct.role == ClientContactRole.primary:
            ct.role = ClientContactRole.other
        ct.full_name = BORRADO
        ct.email = ct.phone = ct.job_title = ct.notes = None
        if ct.is_active:
            ct.deactivated_at = ahora
        ct.is_active = False
    for u in usuarios:
        u.full_name = BORRADO
        u.email = f"{_seudonimo(u.id)}@erased.invalid"
        u.phone = u.job_title = None
        u.company = None   # M81: la empresa también identifica (antes quedaba)
        u.hashed_password = None
        # M81: sus sesiones del portal dejan de valer: `is_active=False` lo
        # comprueba cada petición del portal, y sin contraseña no puede volver.
        u.avatar_initials = None
        u.is_active = False
    db.flush()
    return {"client_contacts": len(contactos), "portal_users": len(usuarios)}
