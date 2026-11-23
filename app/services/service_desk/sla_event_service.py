from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.service_desk._enums import ESTADOS_DE_TICKET_RESUELTOS
from app.models.service_desk import SLAEvent, SLAEventType, Ticket, TicketStatus
import logging
from app.core.errores import ErrorDeDominio
from app.core.codigos_de_error import error

logger = logging.getLogger(__name__)


def get_ticket_or_404(db: Session, ticket_id: str) -> Ticket:
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise ErrorDeDominio(404)
    return ticket


from app.services.textos_de_salida_servicios_m_z import texto_para  # noqa: E402
from app.services.textos_guardados import pintar, por_clave_json, idioma_del_lector  # noqa: E402


def pause_ticket_sla(db: Session, ticket_id: str, user_id: str, note: str) -> dict:
    from app.services.service_desk.sla_del_ticket import pausar_sla
    from app.services.sla_service import log_history
    ticket = get_ticket_or_404(db, ticket_id)
    if ticket.sla_paused_at:
        raise error(400, "sla_ya_pausado", detail="SLA ya está pausado")

    pausar_sla(ticket, datetime.now(timezone.utc))
    # Auditoria 2026-11-22 (A-SD1): el cambio de estado no dejaba historial y
    # usaba el texto "pending_client" en vez del estado.
    if _valor(ticket.status) not in ESTADOS_DE_TICKET_RESUELTOS and ticket.status != TicketStatus.pending_client:
        log_history(db, ticket.id, "status", ticket.status, TicketStatus.pending_client, user_id)
        ticket.status = TicketStatus.pending_client

    # Migracion 200: la nota por defecto se guarda tambien por clave; la libre del usuario no.
    clave, datos = (None, None) if note else por_clave_json("sla.nota_pausado")
    event = SLAEvent(
        ticket_id=ticket_id,
        event_type=SLAEventType.paused,
        note=note or texto_para(db, "sla.nota_pausado", user_id=user_id),
        note_key=clave, note_params=datos,
        created_by=user_id,
    )
    db.add(event)
    return {"ok": True, "paused_at": str(ticket.sla_paused_at)}


def pause_ticket_sla_from_payload(db: Session, ticket_id: str, user_id: str, payload: dict) -> dict:
    note = (payload or {}).get("note")
    return pause_ticket_sla(db, ticket_id, user_id, note)


def resume_ticket_sla(db: Session, ticket_id: str, user_id: str) -> dict:
    """Reanuda el reloj del SLA.

    Auditoria 2026-11-22 (A-SD1): sumaba la pausa a `sla_pause_minutes` Y ademas
    movia `sla_response_due`/`sla_resolution_due`; como los lectores vuelven a
    sumar `sla_pause_minutes` al vencimiento, la pausa contaba dos veces. Ahora
    usa la misma funcion que el resto de transiciones: acumula los minutos (en
    el calendario del SLA) y no toca los vencimientos.
    """
    from app.services.service_desk.sla_del_ticket import _reanudar_sla_pausado
    ticket = get_ticket_or_404(db, ticket_id)
    if not ticket.sla_paused_at:
        raise error(400, "sla_no_pausado", detail="SLA no está pausado")

    pause_duration = _reanudar_sla_pausado(ticket, datetime.now(timezone.utc))

    clave, datos = por_clave_json("sla.nota_reanudado", minutos=pause_duration)
    event = SLAEvent(
        ticket_id=ticket_id,
        event_type=SLAEventType.resumed,
        note=texto_para(db, "sla.nota_reanudado", user_id=user_id, minutos=pause_duration),
        note_key=clave, note_params=datos,
        created_by=user_id,
    )
    db.add(event)
    return {"ok": True, "paused_minutes": pause_duration}


def _valor(v):
    return getattr(v, "value", v)


def list_sla_events(db: Session, ticket_id: str) -> list[dict]:
    events = db.query(SLAEvent).filter(
        SLAEvent.ticket_id == ticket_id
    ).order_by(SLAEvent.created_at).all()
    idioma = idioma_del_lector(db)
    return [
        {
            "id": e.id,
            "event_type": e.event_type.value,
            "sla_type": e.sla_type,
            "note": pintar(e.note_key, e.note_params, e.note, idioma),
            "created_at": str(e.created_at),
        }
        for e in events
    ]
