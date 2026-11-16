from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.service_desk import Ticket, TicketComment, TicketStatus
from app.models.user import User
import logging
from app.core.errores import ErrorDeDominio
from app.core.codigos_de_error import error as error_con_codigo

logger = logging.getLogger(__name__)


# La guarda vive en `scoping.py`, junto a `scope_ticket_query`, de la que
# depende. Se reexporta con el mismo nombre para que ningun sitio de llamada
# cambie: estaba copiada literalmente en este modulo y en dos mas.
from app.services.service_desk.scoping import (  # noqa: E402,F401
    get_scoped_ticket_or_404,
)


def add_internal_comment(
    db: Session,
    ticket: Ticket,
    ticket_id: str,
    body: str,
    is_public: bool,
    current_user: Optional[User],
    *,
    client_text: Optional[str] = None,
    client_language: Optional[str] = None,
    salida=None,
) -> TicketComment:
    """Comentario de un agente.

    Traduccion en tiempo real (16-11-2026): una respuesta publica sale en el
    idioma del cliente (`traduccion.salida.preparar`): con `client_text` (la
    vista previa, quiza corregida) o, sin ella, traducida sola si la empresa lo
    quiere. `salida` ya preparada (la conversacion de un canal) no se vuelve a
    traducir. Las notas internas (`is_public=False`) no se tocan: jamas salen.
    """
    from app.services.traduccion import salida as _salida
    from app.services.traduccion.mensajes import canal_del_ticket

    if is_public and salida is None:
        salida = _salida.preparar(db, ticket.organization_id, canal_del_ticket(ticket), body, usuario=current_user,
                                  ticket=ticket, texto_cliente=client_text, idioma_cliente=client_language)
    comment = TicketComment(
        ticket_id=ticket_id,
        body=salida.cuerpo if salida is not None else body,
        language=salida.idioma if salida is not None else None,
        is_public=is_public,
        author_user_id=current_user.id if current_user else None,
    )
    db.add(comment)
    if salida is not None and salida.original is not None:
        db.flush()
        _salida.anotar_autor(db, ticket.organization_id, "ticket_comment", comment.id, salida, current_user,
                             "ticket_comment")

    if not ticket.first_response_at and current_user and is_public:
        ticket.first_response_at = datetime.now(timezone.utc)
        if ticket.status == TicketStatus.new:
            ticket.status = TicketStatus.in_progress

    return comment


def get_client_ticket_or_404(db: Session, ticket_id: str, client_id: str) -> Ticket:
    """Ticket acotado al cliente de portal solicitante.

    client_id es OBLIGATORIO: sin este filtro cualquier cliente autenticado del
    portal podría comentar (is_public=True) en el ticket de otro cliente (IDOR).
    404 en lugar de 403 para no revelar la existencia del ticket ajeno.
    """
    ticket = (
        db.query(Ticket)
        .filter(Ticket.id == ticket_id, Ticket.requester_client_id == client_id)
        .first()
    )
    if not ticket:
        raise error_con_codigo(404, "ticket_no_encontrado")
    return ticket


def add_client_comment(db: Session, ticket: Ticket, ticket_id: str, body: str, client_id: str) -> TicketComment:
    comment = TicketComment(
        ticket_id=ticket_id,
        body=body,
        is_public=True,
        author_client_id=client_id,
    )
    db.add(comment)

    if ticket.status == TicketStatus.pending_client:
        ticket.status = TicketStatus.in_progress
        if ticket.sla_paused_at:
            paused_at = ticket.sla_paused_at
            if paused_at.tzinfo is None:
                paused_at = paused_at.replace(tzinfo=timezone.utc)
            paused_minutes = int((datetime.now(timezone.utc) - paused_at).total_seconds() / 60)
            ticket.sla_pause_minutes = (ticket.sla_pause_minutes or 0) + paused_minutes
            ticket.sla_paused_at = None

    return comment
