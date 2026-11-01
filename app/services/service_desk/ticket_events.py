"""Bandeja de salida de eventos de ticket (`sd_ticket_events`).

Auditoria 2026-11. Ningun cambio de ticket avisaba a nadie: ni el solicitante
recibia acuse ni respuesta, ni el agente sabia que le habian asignado algo. Las
plantillas `ticket_assigned` / `ticket_replied` / `ticket_resolved` existian y
nadie las usaba, y `EventType.TICKET_*` no se emitia nunca, asi que tampoco
salian webhooks.

El evento se registra en el `before_flush` de la sesion y no en cada endpoint:
un ticket cambia por el agente, por el portal, por correo, por SMS, por un
flujo, por una regla de escalado o por la IA, y cada via nueva que se olvide
de avisar es un aviso que no llega. Aqui no se olvida ninguna, porque todas
acaban guardando el ticket.

Lo que se hace con cada evento (avisos, correo, webhooks, flujos) vive en
`ticket_event_processor.py` y corre fuera de la peticion.
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Optional

from sqlalchemy import event, inspect

from app.db.session import TenantSession
from app.models.service_desk import Ticket, TicketComment, TicketEvent

logger = logging.getLogger(__name__)

#: Campo del ticket -> tipo de evento cuando cambia.
CAMPOS_VIGILADOS = {
    "assigned_to_user_id": "assigned",
    "assigned_group_id": "group_assigned",
    "status": "status_changed",
    "priority": "priority_changed",
}

_PENDIENTES = "sd_eventos_pendientes"


def _valor(v: Any) -> Any:
    return getattr(v, "value", v)


def _actor_de_la_sesion(session) -> Optional[str]:
    return getattr(session.info.get("current_user"), "id", None)


def registrar(
    session,
    ticket: Ticket,
    kind: str,
    data: Optional[dict] = None,
    *,
    actor_user_id: Optional[str] = None,
    actor_client_id: Optional[str] = None,
) -> TicketEvent:
    """Anota un evento del ticket en la bandeja; se guarda con la transaccion.

    Para los eventos que no salen de un cambio de columna —SLA en riesgo,
    escalado, aprobacion— y para los que si, desde el escuchador.
    """
    if ticket.id is None:
        ticket.id = str(uuid.uuid4())
    origen = session.info.get("sd_origen")
    if origen:
        # Lo hizo un flujo (o la escalada): sirve para no encadenar flujos.
        data = {**(data or {}), "origin": origen}
    ev = TicketEvent(
        id=str(uuid.uuid4()),
        organization_id=ticket.organization_id or session.info.get("organization_id"),
        ticket_id=ticket.id,
        kind=kind,
        data=json.dumps(data or {}, default=str),
        actor_user_id=actor_user_id if actor_user_id is not None else _actor_de_la_sesion(session),
        actor_client_id=actor_client_id,
    )
    session.add(ev)
    session.info[_PENDIENTES] = True
    return ev


def _al_crear_ticket(session, ticket: Ticket) -> None:
    registrar(session, ticket, "created", {"source": ticket.source},
              actor_user_id=ticket.created_by_user_id,
              actor_client_id=ticket.requester_client_id)


def _al_comentar(session, comment: TicketComment) -> None:
    ticket = comment.ticket
    if ticket is None and comment.ticket_id:
        with session.no_autoflush:
            ticket = session.get(Ticket, comment.ticket_id)
    if ticket is None:
        return
    if comment.id is None:
        comment.id = str(uuid.uuid4())
    registrar(
        session, ticket, "commented",
        {"comment_id": comment.id, "is_public": bool(comment.is_public)},
        actor_user_id=comment.author_user_id,
        actor_client_id=comment.author_client_id,
    )


def _al_cambiar_ticket(session, ticket: Ticket) -> None:
    estado = inspect(ticket)
    for campo, kind in CAMPOS_VIGILADOS.items():
        hist = estado.attrs[campo].history
        if not hist.has_changes():
            continue
        antes = _valor(hist.deleted[0]) if hist.deleted else None
        despues = _valor(hist.added[0]) if hist.added else None
        if antes == despues:
            continue
        registrar(session, ticket, kind, {"old": antes, "new": despues})


def _antes_de_guardar(session, flush_context, instances) -> None:
    for obj in list(session.new):
        if isinstance(obj, Ticket):
            _al_crear_ticket(session, obj)
        elif isinstance(obj, TicketComment):
            _al_comentar(session, obj)
    for obj in list(session.dirty):
        if isinstance(obj, Ticket) and session.is_modified(obj, include_collections=False):
            _al_cambiar_ticket(session, obj)


def _tras_confirmar(session) -> None:
    """Con la transaccion ya escrita, pide al worker que procese la bandeja.

    Si el broker no responde no pasa nada: la tarea periodica la recoge en el
    siguiente minuto. `retry=False` para no colgar la peticion esperando a
    Redis.
    """
    if not session.info.pop(_PENDIENTES, False):
        return
    try:
        from app.worker import sd_procesar_eventos_de_ticket
        sd_procesar_eventos_de_ticket.apply_async(retry=False)
    except Exception as exc:
        logger.debug("bandeja de tickets: sin broker, la recoge la tarea periodica (%s)", exc)


def _tras_deshacer(session) -> None:
    session.info.pop(_PENDIENTES, None)


event.listen(TenantSession, "before_flush", _antes_de_guardar)
event.listen(TenantSession, "after_commit", _tras_confirmar)
event.listen(TenantSession, "after_soft_rollback", lambda session, previous: _tras_deshacer(session))
