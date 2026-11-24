"""Tiempo real del chat del portal (24-11-2026, docs/portal/CHAT_DEL_PORTAL.md).

Va por los dos WebSocket que ya existen (el mismo transporte que el chat en vivo
del service desk, `service_desk/canales_en_vivo._empujar`: Redis si lo hay, si
no las conexiones de este proceso):

- Operadores: `/ws/notifications` (clave = id de usuario).
- Clientes: `/ws/portal-notifications` (clave `client:<id>`).

Lo que se empuja es `{"type": "portal_conv", "event": <evento>,
"conversation_id": ..., ...}` SOLO a los participantes de la conversación (de su
empresa). Eventos: `message` (nuevo, editado o borrado), `reaction`, `read`,
`typing` y `call` (con `call_id`, `status`, `kind`). Nunca viaja el contenido
de un mensaje: el aviso dice «hay cambios» y cada lado los pide por la API, que
aplica sus permisos (p. ej. el cliente no ve notas internas).

Lo que llega por el socket: `{"type": "portal_conv_typing", "conversation_id"}`
(escribiendo). Se comprueba que quien lo manda participa en la conversación.

Si el socket no está, las pantallas siguen con su sondeo: nada depende de que
el aviso llegue.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

TIPO = "portal_conv"
#: Mensajes que entiende cada WebSocket.
ESCRIBIENDO = "portal_conv_typing"

EnSesion = Callable[..., Awaitable[Any]]


def clave_de_cliente(client_user_id: str) -> str:
    return f"client:{client_user_id}"


def _clientes_de_la_conversacion(db: Session, conversation) -> set[str]:
    """Usuarios del portal que ven la conversación: los apuntados y los de su cliente."""
    from app.models.client_portal import ClientUser

    ids: set[str] = set()
    orgs_cliente: set[str] = set()
    for p in conversation.participants:
        if p.removed_at is not None:
            continue
        if p.client_user_id:
            ids.add(p.client_user_id)
        elif p.client_org_id and not p.user_id:
            orgs_cliente.add(p.client_org_id)
    if conversation.created_by_client_id:
        ids.add(conversation.created_by_client_id)
    if orgs_cliente:
        filas = db.query(ClientUser.id).filter(
            ClientUser.client_org_id.in_(orgs_cliente),
            ClientUser.organization_id == conversation.organization_id,
            ClientUser.is_active == True,  # noqa: E712
        ).all()
        ids.update(r[0] for r in filas)
    return ids


def _equipo_de_la_conversacion(conversation) -> set[str]:
    ids = {p.user_id for p in conversation.participants if p.removed_at is None and p.user_id}
    if conversation.created_by_user_id:
        ids.add(conversation.created_by_user_id)
    return ids


def destinos(db: Session, conversation, *, incluir_clientes: bool = True,
             excepto_usuario: Optional[str] = None, excepto_cliente: Optional[str] = None) -> list[str]:
    salida = [u for u in _equipo_de_la_conversacion(conversation) if u != excepto_usuario]
    if incluir_clientes:
        salida += [clave_de_cliente(c) for c in _clientes_de_la_conversacion(db, conversation) if c != excepto_cliente]
    return salida


def avisar(db: Session, conversation, evento: str, datos: Optional[dict] = None, *,
           incluir_clientes: bool = True, excepto_usuario: Optional[str] = None,
           excepto_cliente: Optional[str] = None) -> None:
    """Empuja el evento a los participantes. Nunca lanza: el aviso es un extra.

    Llamar DESPUÉS de `db.commit()`: el otro lado pide los datos en cuanto llega.
    """
    try:
        from app.services.service_desk.canales_en_vivo import _empujar
        lista = destinos(db, conversation, incluir_clientes=incluir_clientes,
                         excepto_usuario=excepto_usuario, excepto_cliente=excepto_cliente)
        _empujar(lista, {"type": TIPO, "event": evento, "conversation_id": conversation.id,
                         "ts": datetime.now(timezone.utc).isoformat(), **(datos or {})})
    except Exception:
        logger.debug("chat del portal: aviso en vivo no entregado", exc_info=True)


# ── Lo que llega por los WebSocket ────────────────────────────────────────────

def _escribiendo_operador(db: Session, usuario, conversation_id: str) -> None:
    from app.core.capacidades import tiene
    from app.services.portal_conversation_service._comun import _conversacion_del_equipo
    if not tiene(db, usuario, "clientes.gestionar"):
        return
    try:
        conv = _conversacion_del_equipo(db, conversation_id, usuario)
    except ValueError:
        return
    avisar(db, conv, "typing", {"who": "team", "name": usuario.full_name}, excepto_usuario=usuario.id)


def _escribiendo_cliente(db: Session, cliente, conversation_id: str) -> None:
    from app.services.portal_conversation_service._comun import _conversacion_del_cliente
    try:
        conv = _conversacion_del_cliente(db, conversation_id, cliente)
    except ValueError:
        return
    # El cliente no avisa a otros clientes de su empresa: solo al equipo.
    avisar(db, conv, "typing", {"who": "client", "name": cliente.full_name}, incluir_clientes=False)


def _id(msg: dict) -> Optional[str]:
    valor = str(msg.get("conversation_id") or "")[:36]
    return valor or None


async def mensaje_del_operador(en_sesion: EnSesion, db: Session, usuario, msg: dict) -> bool:
    """Atiende un mensaje del WebSocket de operadores. True si era del chat del portal."""
    if msg.get("type") != ESCRIBIENDO:
        return False
    conv_id = _id(msg)
    if conv_id and not conv_id.startswith("legacy:"):
        await en_sesion(_escribiendo_operador, db, usuario, conv_id)
    return True


async def mensaje_del_portal(en_sesion: EnSesion, db: Session, cliente, msg: dict) -> bool:
    """Atiende un mensaje del WebSocket del portal. True si era del chat del portal."""
    if msg.get("type") != ESCRIBIENDO:
        return False
    conv_id = _id(msg)
    if conv_id and not conv_id.startswith("legacy:"):
        await en_sesion(_escribiendo_cliente, db, cliente, conv_id)
    return True
