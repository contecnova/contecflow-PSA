"""
ws_service.py — Helpers de base de datos para el endpoint WebSocket.

Centraliza las consultas necesarias para notificaciones en tiempo real,
separando la lógica de BD del transporte WebSocket.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Tuple, List, Dict, Any

from sqlalchemy.orm import Session


def get_unread_notifications(
    db: Session, user_id: str
) -> Tuple[int, List[Any]]:
    """Devuelve (count, notifs) de notificaciones no leídas del usuario."""
    from app.models.enterprise import Notification

    q = (
        db.query(Notification)
        .filter(Notification.user_id == user_id, Notification.is_read == False)  # noqa: E712
        .order_by(Notification.created_at.desc())
        .limit(50)
    )
    items = q.all()
    return len(items), items


def mark_notification_read(db: Session, notification_id: str, user_id: str) -> None:
    """Marca una notificación como leída si pertenece al usuario."""
    from app.models.enterprise import Notification

    notif = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == user_id)
        .first()
    )
    if notif and not notif.is_read:
        notif.is_read = True
        notif.read_at = datetime.now(timezone.utc)
        db.commit()


def get_portal_poll_data(db: Session, client_id: str) -> Dict[str, Any]:
    """
    Devuelve un dict con los contadores de interés para el portal cliente:
      - unread_messages: mensajes dirigidos al cliente aún no leídos
      - open_tickets: tickets abiertos del cliente
      - recent_public_comments: respuestas públicas recientes en sus tickets
    """
    from app.models.client_portal import ClientMessage
    from app.models.service_desk import Ticket, TicketComment, TicketStatus

    # Mensajes no leídos por el cliente (enviados por el equipo interno)
    unread_messages: int = (
        db.query(ClientMessage)
        .filter(
            ClientMessage.sender_client_id != client_id,
            ClientMessage.is_read_by_client == False,  # noqa: E712
            ClientMessage.is_internal == False,  # noqa: E712
        )
        .count()
    )

    # Tickets abiertos del cliente (excluyendo cerrados/cancelados)
    closed_statuses = {TicketStatus.resolved, TicketStatus.closed, TicketStatus.cancelled}
    open_tickets: int = (
        db.query(Ticket)
        .filter(
            Ticket.requester_client_id == client_id,
            Ticket.status.notin_(closed_statuses),
        )
        .count()
    )

    # Comentarios públicos recientes (últimas 24 h) en tickets del cliente
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    client_ticket_ids = (
        db.query(Ticket.id)
        .filter(Ticket.requester_client_id == client_id)
        .scalar_subquery()
    )
    recent_public_comments = (
        db.query(TicketComment)
        .filter(
            TicketComment.ticket_id.in_(client_ticket_ids),
            TicketComment.is_public == True,  # noqa: E712
            TicketComment.author_client_id != client_id,
            TicketComment.created_at >= since,
        )
        .order_by(TicketComment.created_at.desc())
        .limit(10)
        .all()
    )

    return {
        "unread_messages": unread_messages,
        "open_tickets": open_tickets,
        "recent_public_comments": recent_public_comments,
    }
