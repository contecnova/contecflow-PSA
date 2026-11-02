from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.service_desk import SLAPolicy, Ticket
from app.schemas.service_desk import TicketUpdateIn
from app.services.service_desk.status_compat import normalize_ticket_status
from app.services.service_desk.dynamic_ticket_fields_service import save_ticket_dynamic_fields
from app.services.service_desk.ticket_ops_service import save_pending_snapshot
from app.services.sla_service import (
    PRIORITY_MATRIX,
    calculate_sla_due as _calculate_sla_due,
    log_history as _log_history,
    norm_enum as _norm_enum,
)
import logging

logger = logging.getLogger(__name__)


# La guarda vive en `scoping.py`, junto a `scope_ticket_query`, de la que
# depende. Se reexporta con el mismo nombre para que ningun sitio de llamada
# cambie: estaba copiada literalmente en este modulo y en dos mas.
from app.services.service_desk.scoping import (  # noqa: E402,F401
    get_scoped_ticket_or_404,
)


# ── Actualizacion de un ticket ───────────────────────────────────────────────
#
# Auditoria 2026-08 (hallazgo 18). `apply_ticket_update` eran 117 lineas de
# complejidad 29 sin un solo test, y contenian una DUPLICACION literal: el
# bloque que acumula el tiempo en pausa y reanuda el reloj del SLA aparecia dos
# veces, en la rama `in_progress` y en el `else`.
#
# Ahora cada transicion de estado es su funcion y `_POR_ESTADO` es la tabla. La
# equivalencia se verifico sobre 23 casos —cada estado, con y sin primera
# respuesta, con SLA vencido y a tiempo, con pausa acumulada y con pausa sin
# zona horaria— comparando el ticket resultante campo por campo: identico.

def _aware(dt):
    """Interpreta un datetime sin zona como UTC.

    Los timestamps almacenados SON UTC (ver app/core/timeutil.py), así que
    tratarlos como hora local los desplazaría por el offset del servidor.
    """
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


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


def _marcar_primera_respuesta(ticket, now) -> None:
    """Sella la primera respuesta si aún no la tenía, y evalúa su SLA.

    Compartido por `in_progress` y `resolved`: un ticket puede resolverse sin
    haber pasado por «en progreso», y en ese caso la primera respuesta es esa
    misma resolución.
    """
    if ticket.first_response_at:
        return
    ticket.first_response_at = now
    if ticket.created_at:
        ticket.first_response_minutes = int(
            (now - _aware(ticket.created_at)).total_seconds() / 60
        )


def _vencido(due, ticket, now) -> bool:
    """¿Se ha incumplido un vencimiento de SLA, descontando las pausas?

    Los minutos en pausa se SUMAN al vencimiento: el reloj no corre mientras se
    espera al cliente, así que no contarlos marcaría como incumplido un SLA que
    se respetó.
    """
    efectivo = _aware(due) + timedelta(minutes=ticket.sla_pause_minutes or 0)
    return now > efectivo


def _estado_en_progreso(db, ticket, now) -> None:
    """Paso a «en progreso»: sella la primera respuesta y reanuda el SLA."""
    if not ticket.first_response_at:
        _marcar_primera_respuesta(ticket, now)
        if ticket.sla_response_due:
            ticket.sla_response_breached = _vencido(ticket.sla_response_due, ticket, now)
    _reanudar_sla_pausado(ticket, now)


def _estado_resuelto(db, ticket, now) -> None:
    """Resolución: sella los tiempos y evalúa el SLA de resolución."""
    ticket.resolved_at = now
    _marcar_primera_respuesta(ticket, now)
    if ticket.created_at:
        ticket.resolution_minutes = int(
            (now - _aware(ticket.created_at)).total_seconds() / 60
        )
    if ticket.sla_resolution_due:
        ticket.sla_resolution_breached = _vencido(ticket.sla_resolution_due, ticket, now)


def _estado_cerrado(db, ticket, now) -> None:
    """Cierre: sella la fecha y pide la encuesta de satisfacción una sola vez."""
    ticket.closed_at = now
    if not ticket.csat_requested_at:
        ticket.csat_requested_at = now


def _estado_en_espera(db, ticket, now) -> None:
    """En espera del cliente o de un tercero: para el reloj del SLA.

    Se guarda una instantánea antes de parar, para poder reconstruir qué estado
    tenía el ticket cuando se dejó en espera.
    """
    save_pending_snapshot(db, ticket)
    ticket.sla_paused_at = now


# Estado normalizado → qué hacer al entrar en él. El `else` del original —el
# resto de estados— sólo reanudaba el SLA, y eso es `_reanudar_sla_pausado`.
_POR_ESTADO = {
    "in_progress": _estado_en_progreso,
    "resolved": _estado_resuelto,
    "closed": _estado_cerrado,
    "pending_client": _estado_en_espera,
    "pending_third": _estado_en_espera,
}


def _aplicar_estado(db, ticket, normalized_status, now) -> None:
    """Aplica los efectos de una transición de estado.

    Un estado sin efectos propios sólo reanuda el SLA si estaba en pausa, que es
    lo que hacía la rama `else` de la versión original.
    """
    accion = _POR_ESTADO.get(normalized_status)
    if accion is None:
        _reanudar_sla_pausado(ticket, now)
        return
    accion(db, ticket, now)


def _recalcular_prioridad(db, ticket, payload) -> None:
    """Recalcula prioridad y vencimientos de SLA al cambiar urgencia o impacto.

    No se toca si quien llama ha fijado la prioridad a mano: una decisión
    explícita manda sobre la matriz. Y no se recalculan los vencimientos de un
    ticket ya resuelto, cerrado o cancelado — su reloj ya paró.
    """
    if payload.priority:
        return
    new_priority = PRIORITY_MATRIX.get(
        (_norm_enum(ticket.urgency), _norm_enum(ticket.impact)),
        "p3_medium",
    )
    old_priority = ticket.priority
    ticket.priority = new_priority
    if new_priority == old_priority:
        return
    if ticket.status in ("resolved", "closed", "cancelled"):
        return
    sla_policy = (
        db.query(SLAPolicy).filter(SLAPolicy.id == ticket.sla_policy_id).first()
        if ticket.sla_policy_id
        else None
    )
    # Se recalcula desde la apertura: cambiar la prioridad no reinicia el reloj.
    resp_due, res_due = _calculate_sla_due(
        new_priority, sla_policy, db=db,
        org_id=ticket.organization_id, start=ticket.created_at,
    )
    ticket.sla_response_due = resp_due
    ticket.sla_resolution_due = res_due


def apply_ticket_update(
    db: Session,
    ticket: Ticket,
    ticket_id: str,
    payload: TicketUpdateIn,
    current_user_id: str,
    old_assigned_to: str,
    old_support_level,
    organization_id: str | None = None,
) -> dict:
    changes = payload.model_dump(exclude_unset=True)
    dynamic_fields = changes.pop("dynamic_fields", None)
    normalized_status = normalize_ticket_status(payload.status)
    from app.services.service_desk.catalog_approval_service import exigir_aprobado
    exigir_aprobado(ticket, normalized_status)
    if "status" in changes:
        changes["status"] = normalized_status

    for field, new_val in changes.items():
        old_val = getattr(ticket, field, None)
        _log_history(db, ticket_id, field, old_val, new_val, current_user_id)
        setattr(ticket, field, new_val)

    now = datetime.now(timezone.utc)

    if normalized_status:
        _aplicar_estado(db, ticket, normalized_status, now)

    if payload.urgency or payload.impact:
        _recalcular_prioridad(db, ticket, payload)

    if payload.tags is not None:
        ticket.tags = payload.tags

    if payload.support_level:
        _log_history(db, ticket_id, "escalation", old_support_level, payload.support_level, current_user_id)

    if dynamic_fields is not None:
        save_ticket_dynamic_fields(db, ticket_id, dynamic_fields)
        _log_history(db, ticket_id, "dynamic_fields", "updated", "updated", current_user_id)

    return {
        "refresh_profile": normalized_status in ("resolved", "closed") and bool(ticket.assigned_to_user_id),
        "reassigned": bool(payload.assigned_to_user_id and old_assigned_to and payload.assigned_to_user_id != old_assigned_to),
        "record_routing_outcome": normalized_status in ("resolved", "closed"),
    }
