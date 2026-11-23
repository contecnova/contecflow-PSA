from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.service_desk._enums import ESTADOS_DE_TICKET_RESUELTOS
from app.models.service_desk import Ticket, TicketStatus
import logging
from app.core.errores import ErrorDeDominio
from app.core.codigos_de_error import error as error_con_codigo

logger = logging.getLogger(__name__)

#: Escala de la encuesta de satisfaccion (`TicketCsatIn.score`, 1-5).
CSAT_MIN, CSAT_MAX = 1, 5


def submit_ticket_csat(
    db: Session, ticket_id: str, client_id: str, score: int, comment: str = None,
) -> dict:
    # client_id es OBLIGATORIO: el CSAT llega desde el portal de cliente y solo el
    # cliente solicitante puede puntuar su propio ticket. Sin este filtro cualquier
    # cliente autenticado podría puntuar —y cerrar— el ticket de otro (IDOR).
    # 404 en lugar de 403 para no revelar la existencia del ticket ajeno.
    # Auditoria 2026-11-22 (servicios m-z, 4.3): la puntuacion va de 1 a 5;
    # antes se guardaba cualquier entero y descuadraba las medias de CSAT.
    if not isinstance(score, int) or isinstance(score, bool) or not CSAT_MIN <= score <= CSAT_MAX:
        raise error_con_codigo(422, "interno_puntuacion_fuera_de_rango", min=CSAT_MIN, max=CSAT_MAX)
    ticket = (
        db.query(Ticket)
        .filter(Ticket.id == ticket_id, Ticket.requester_client_id == client_id)
        .first()
    )
    if not ticket:
        raise error_con_codigo(404, "ticket_no_encontrado")
    if ticket.status not in ESTADOS_DE_TICKET_RESUELTOS:
        raise error_con_codigo(400, "solo_tickets_resueltos")

    ticket.csat_score = score
    ticket.csat_comment = comment
    if ticket.status == "resolved":
        ticket.status = TicketStatus.closed
        ticket.closed_at = datetime.now(timezone.utc)

    return {"ok": True}
