from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.service_desk import Ticket, TicketStatus
import logging
from app.core.errores import ErrorDeDominio

logger = logging.getLogger(__name__)


def submit_ticket_csat(
    db: Session, ticket_id: str, client_id: str, score: int, comment: str = None,
) -> dict:
    # client_id es OBLIGATORIO: el CSAT llega desde el portal de cliente y solo el
    # cliente solicitante puede puntuar su propio ticket. Sin este filtro cualquier
    # cliente autenticado podría puntuar —y cerrar— el ticket de otro (IDOR).
    # 404 en lugar de 403 para no revelar la existencia del ticket ajeno.
    ticket = (
        db.query(Ticket)
        .filter(Ticket.id == ticket_id, Ticket.requester_client_id == client_id)
        .first()
    )
    if not ticket:
        raise ErrorDeDominio(404, "Ticket no encontrado")
    if ticket.status not in ["resolved", "closed"]:
        raise ErrorDeDominio(400, "Solo tickets resueltos")

    ticket.csat_score = score
    ticket.csat_comment = comment
    if ticket.status == "resolved":
        ticket.status = TicketStatus.closed
        ticket.closed_at = datetime.now(timezone.utc)

    return {"ok": True}
