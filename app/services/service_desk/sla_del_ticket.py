"""Reloj del SLA de un ticket: reanudar tras una pausa y cambiar la prioridad.

Vivian en `ticket_update_service`, y `ticket_ops_service` (que este importa)
los traia dentro de una funcion: un ciclo escondido (auditoria 2026-11, #43).
Aqui no dependen de ninguno de los dos; `ticket_update_service` los reexporta.
"""
from datetime import timezone

from app.models.service_desk import SLAPolicy
from app.services.sla_service import calculate_sla_due as _calculate_sla_due, norm_enum as _norm_enum


def _reanudar_sla_pausado(ticket, now) -> None:
    """Acumula el tiempo en pausa y reanuda el reloj del SLA.

    Auditoría 2026-08 (hallazgo 18). Este bloque estaba DUPLICADO literalmente:
    una vez en la rama `in_progress` y otra en el `else` que cubre el resto de
    estados. Dos copias del mismo cálculo de minutos son dos sitios donde
    corregir un error y uno donde olvidarlo.
    """
    if not ticket.sla_paused_at:
        return
    paused_at = ticket.sla_paused_at
    if paused_at.tzinfo is None:
        paused_at = paused_at.replace(tzinfo=timezone.utc)
    paused_mins = int((now - paused_at).total_seconds() / 60)
    ticket.sla_pause_minutes = (ticket.sla_pause_minutes or 0) + paused_mins
    ticket.sla_paused_at = None


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
    if ticket.status in ("resolved", "closed", "cancelled"):
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
