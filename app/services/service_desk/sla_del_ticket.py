"""Reloj del SLA de un ticket: reanudar tras una pausa y cambiar la prioridad.

Vivian en `ticket_update_service`, y `ticket_ops_service` (que este importa)
los traia dentro de una funcion: un ciclo escondido (auditoria 2026-11, #43).
Aqui no dependen de ninguno de los dos; `ticket_update_service` los reexporta.
"""
import logging
from datetime import timezone

from sqlalchemy.orm import object_session

from app.models.service_desk._enums import ESTADOS_DE_TICKET_CERRADOS
from app.models.service_desk import SLAPolicy
# `calendario_del_ticket` vive en `sla_service` (prueba global 23-11-2026: desde
# aqui cerraba el ciclo sla_service -> sla_del_ticket -> sla_service); se reexporta.
from app.services.sla_service import (  # noqa: F401
    calculate_sla_due as _calculate_sla_due,
    calendario_del_ticket,
    calendario_sla,
    horas_sla_entre,
    norm_enum as _norm_enum,
)

logger = logging.getLogger(__name__)


def pausar_sla(ticket, now) -> bool:
    """Para el reloj del SLA. Si ya estaba parado, no hace nada y devuelve False.

    Auditoria 2026-11-22 (A-SD3): pasar de una espera a otra (cliente →
    tercero) volvia a poner `sla_paused_at = now` y se perdia el tiempo ya
    pausado. Ahora la pausa empieza una sola vez y se cierra al reanudar.
    """
    if ticket.sla_paused_at:
        return False
    ticket.sla_paused_at = now
    return True


def _reanudar_sla_pausado(ticket, now) -> None:
    """Acumula el tiempo en pausa y reanuda el reloj del SLA.

    Auditoría 2026-08 (hallazgo 18). Este bloque estaba DUPLICADO literalmente:
    una vez en la rama `in_progress` y otra en el `else` que cubre el resto de
    estados. Dos copias del mismo cálculo de minutos son dos sitios donde
    corregir un error y uno donde olvidarlo.
    """
    if not ticket.sla_paused_at:
        return 0
    paused_at = ticket.sla_paused_at
    if paused_at.tzinfo is None:
        paused_at = paused_at.replace(tzinfo=timezone.utc)
    # Auditoria 2026-11-22 (A-SD2): minutos del CALENDARIO del SLA, no de pared.
    # Los vencimientos se calculan en horario laboral; sumarles la pausa en
    # reloj de pared (viernes 17:00 → lunes 9:00 = ~64 h) ocultaba
    # incumplimientos. Los lectores suman estos minutos con el mismo calendario
    # (`sla_service.vencimiento_efectivo`).
    try:
        db = object_session(ticket)
    except Exception:   # no es una fila del ORM (p. ej. un ticket en memoria)
        logger.debug("_reanudar_sla_pausado: excepcion ignorada", exc_info=True)
        db = None
    try:
        if db is None:
            raise LookupError("ticket sin sesion")
        cal = calendario_del_ticket(db, ticket)
        paused_mins = int(round(horas_sla_entre(paused_at, now, cal) * 60))
    except Exception:
        # Sin sesion o sin calendario legible: el criterio anterior (pared),
        # mejor que perder la pausa.
        logger.warning("pausa del SLA del ticket %s en reloj de pared: sin calendario",
                       getattr(ticket, "id", None), exc_info=True)
        paused_mins = int((now - paused_at).total_seconds() / 60)
    ticket.sla_pause_minutes = (ticket.sla_pause_minutes or 0) + paused_mins
    ticket.sla_paused_at = None
    return paused_mins


def cambiar_prioridad(db, ticket, nueva) -> bool:
    """Unica via para cambiar la prioridad fuera del PATCH: recalcula los plazos.

    La usan la escalada, el incidente mayor, el triaje de IA, la sincronizacion
    con Jira y «volver al estado anterior». Devuelve si cambio.
    """
    antes = _norm_enum(ticket.priority)
    ticket.priority = nueva
    if _norm_enum(ticket.priority) == antes:
        return False
    _recalcular_vencimientos(db, ticket)
    return True


def _recalcular_vencimientos(db, ticket) -> None:
    """Vencimientos del SLA para la prioridad actual, desde la apertura.

    Auditoria 2026-11: fijar la prioridad a mano no los recalculaba (solo lo
    hacia la matriz de urgencia e impacto), y el ticket seguia venciendo con
    los plazos de la prioridad anterior.
    """
    if ticket.status in ESTADOS_DE_TICKET_CERRADOS:
        return
    sla_policy = (
        db.query(SLAPolicy).filter(SLAPolicy.id == ticket.sla_policy_id).first()
        if ticket.sla_policy_id
        else None
    )
    # Se recalcula desde la apertura: cambiar la prioridad no reinicia el reloj.
    resp_due, res_due = _calculate_sla_due(
        _norm_enum(ticket.priority), sla_policy, db=db,
        org_id=ticket.organization_id, start=ticket.created_at,
    )
    ticket.sla_response_due = resp_due
    ticket.sla_resolution_due = res_due
    # SLA condicionales (mejoras de mercado 16-11-2026): si una regla de la
    # empresa encaja con el ticket, sus objetivos mandan sobre los de la politica.
    from app.services.service_desk.reglas_sla import aplicar_regla
    aplicar_regla(db, ticket)
