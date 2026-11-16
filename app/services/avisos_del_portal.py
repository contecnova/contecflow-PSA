"""Avisos de la campana del portal de cliente.

16-11-2026 (campana de notificaciones). El cliente recibía por correo las
respuestas y los cambios de sus tickets, pero en el portal no le quedaba nada:
la campana de la cabecera sólo sumaba contadores y llevaba a Soporte. Ahora cada
aviso que se le manda también queda en su bandeja del portal.

No hay una tabla nueva: `CollaborationNotification` ya tiene destinatario
cliente (`client_user_id`), organización, título, cuerpo, `payload` y estado de
lectura, y es la que lista `/portal/collaboration/notifications`. El `payload`
lleva adónde lleva el aviso en el portal (`seccion` y, si hay, `ticket_id`) y
su `tipo`, con el que el portal pone la etiqueta en el idioma del cliente.

Multi-tenant: cada aviso se crea con la organización del hecho que lo produce y
sólo para clientes de esa organización.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.sin_emojis import sin_emojis
from app.models.client_portal import ClientUser, client_user_projects
from app.models.collaboration import CollaborationNotification, NotificationKind

logger = logging.getLogger(__name__)

#: Largo máximo del título (la columna es de 200) y del extracto.
_TITULO = 200
_CUERPO = 1000


def avisar_al_cliente(
    db: Session,
    *,
    organization_id: Optional[str],
    client_user_id: str,
    titulo: str,
    cuerpo: Optional[str] = None,
    tipo: str = "system",
    seccion: Optional[str] = None,
    ticket_id: Optional[str] = None,
) -> Optional[CollaborationNotification]:
    """Deja un aviso en la campana del portal del cliente. No confirma.

    Sin organización no se crea: la columna es obligatoria y un aviso sin
    organización no se podría acotar a un tenant.
    """
    if not organization_id or not client_user_id:
        return None
    payload = {"tipo": tipo}
    if seccion:
        payload["seccion"] = seccion
    if ticket_id:
        payload["ticket_id"] = ticket_id
    n = CollaborationNotification(
        organization_id=organization_id,
        client_user_id=client_user_id,
        kind=NotificationKind.system,
        title=(sin_emojis(titulo) or "")[:_TITULO],
        body=(cuerpo or "")[:_CUERPO] or None,
        payload=payload,
    )
    db.add(n)
    return n


def clientes_del_proyecto(db: Session, project_id: str, organization_id: str) -> list[str]:
    """Los clientes activos de la organización con acceso al proyecto (el
    proyecto principal o la relación `client_user_projects`)."""
    por_relacion = select(client_user_projects.c.client_user_id).where(
        client_user_projects.c.project_id == project_id)
    filas = db.query(ClientUser.id).filter(
        ClientUser.organization_id == organization_id,
        ClientUser.is_active == True,  # noqa: E712
        or_(ClientUser.project_id == project_id, ClientUser.id.in_(por_relacion)),
    ).all()
    return [f[0] for f in filas]


def avisar_mensaje_del_equipo(db: Session, mensaje, autor) -> int:
    """Un mensaje del equipo al proyecto: aviso a cada cliente del proyecto.

    Las notas internas no salen. No confirma; devuelve cuántos avisos creó.
    """
    if getattr(mensaje, "is_internal", False) or not getattr(mensaje, "project_id", None):
        return 0
    org = getattr(mensaje, "organization_id", None) or getattr(autor, "organization_id", None)
    if not org:
        return 0
    titulo = (mensaje.subject or "").strip() or (getattr(autor, "full_name", None) or "")
    extracto = " ".join((mensaje.body or "").split())[:280]
    creados = 0
    for cid in clientes_del_proyecto(db, mensaje.project_id, org):
        if avisar_al_cliente(db, organization_id=org, client_user_id=cid, titulo=titulo,
                             cuerpo=extracto, tipo="mensaje_del_equipo", seccion="messages"):
            creados += 1
    return creados
