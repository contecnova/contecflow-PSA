from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.service_desk._enums import ESTADOS_DE_TICKET_RESUELTOS
from app.models.service_desk import Ticket
from app.schemas.service_desk import TicketUpdateIn
from app.services.service_desk.status_compat import normalize_ticket_status
from app.services.service_desk.dynamic_ticket_fields_service import save_ticket_dynamic_fields
from app.services.service_desk.ticket_ops_service import save_pending_snapshot
from app.services.service_desk.sla_del_ticket import (  # noqa: F401  (reexportados)
    _reanudar_sla_pausado, _recalcular_vencimientos, calendario_del_ticket, cambiar_prioridad,
    pausar_sla,
)
from app.services.sla_service import (
    PRIORITY_MATRIX,
    log_history as _log_history,
    norm_enum as _norm_enum,
)
import logging
from app.core.codigos_de_error import error

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


def _vencido(due, ticket, now, db=None) -> bool:
    """¿Se ha incumplido un vencimiento de SLA, descontando las pausas?

    Los minutos en pausa se SUMAN al vencimiento: el reloj no corre mientras se
    espera al cliente, así que no contarlos marcaría como incumplido un SLA que
    se respetó. Auditoria 2026-11-22 (A-SD2): se suman en el calendario del SLA
    del ticket, el mismo en que se acumulan.
    """
    from app.services.sla_service import vencimiento_efectivo
    cal = None
    if db is not None and ticket.sla_pause_minutes:
        try:
            cal = calendario_del_ticket(db, ticket)
        except Exception:
            logger.warning("SLA del ticket %s sin calendario; pausa en reloj de pared",
                           getattr(ticket, "id", None), exc_info=True)
    return now > vencimiento_efectivo(due, ticket.sla_pause_minutes, cal)


def _estado_en_progreso(db, ticket, now) -> None:
    """Paso a «en progreso»: sella la primera respuesta y reanuda el SLA."""
    if not ticket.first_response_at:
        _marcar_primera_respuesta(ticket, now)
        if ticket.sla_response_due:
            ticket.sla_response_breached = _vencido(ticket.sla_response_due, ticket, now, db)
    _reanudar_sla_pausado(ticket, now)


def _estado_resuelto(db, ticket, now) -> None:
    """Resolución: sella los tiempos y evalúa el SLA de resolución."""
    ticket.resolved_at = now
    # Resolver un ticket en espera cierra la pausa antes de evaluar el SLA:
    # si no, el tiempo en espera no se descontaba.
    _reanudar_sla_pausado(ticket, now)
    _marcar_primera_respuesta(ticket, now)
    if ticket.created_at:
        ticket.resolution_minutes = int(
            (now - _aware(ticket.created_at)).total_seconds() / 60
        )
    if ticket.sla_resolution_due:
        ticket.sla_resolution_breached = _vencido(ticket.sla_resolution_due, ticket, now, db)


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
    # Auditoria 2026-11-22 (A-SD3): de una espera a otra el reloj sigue parado
    # desde la primera; la instantanea es la del estado ANTERIOR a esperar.
    if ticket.sla_paused_at:
        return
    save_pending_snapshot(db, ticket)
    pausar_sla(ticket, now)


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
    if new_priority != old_priority:
        _recalcular_vencimientos(db, ticket)


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
    # Ciclos de vida por tipo (mejoras de mercado 16-11-2026): un estado propio
    # cae en su estado base, y un estado base elige el estado propio que le toca.
    if "lifecycle_state" in changes or "status" in changes:
        from app.services.service_desk.ciclos_de_vida import resolver_estado
        propio, base = resolver_estado(db, ticket, changes.get("lifecycle_state"),
                                       normalized_status if "status" in changes else None)
        changes["lifecycle_state"] = propio
        if base and base != _norm_enum(ticket.status):
            normalized_status = base
            changes["status"] = base
    from app.services.service_desk.catalog_approval_service import exigir_aprobado
    exigir_aprobado(ticket, normalized_status)
    if "status" in changes:
        changes["status"] = normalized_status
    if changes.get("uc_contract_id"):
        _exigir_contrato_uc(db, changes["uc_contract_id"], ticket.organization_id)
    if changes.pop("uc_vendor_responded", None):
        # Una sola vez y solo mientras se espera al tercero: es lo que para el
        # reloj de respuesta del UC.
        if ticket.uc_started_at is not None and ticket.uc_vendor_responded_at is None:
            changes["uc_vendor_responded_at"] = datetime.now(timezone.utc)

    prioridad_antes = _norm_enum(ticket.priority)
    for field, new_val in changes.items():
        old_val = getattr(ticket, field, None)
        _log_history(db, ticket_id, field, old_val, new_val, current_user_id)
        setattr(ticket, field, new_val)

    now = datetime.now(timezone.utc)

    if normalized_status:
        _aplicar_estado(db, ticket, normalized_status, now)

    if payload.urgency or payload.impact:
        _recalcular_prioridad(db, ticket, payload)
    if payload.priority and _norm_enum(payload.priority) != prioridad_antes:
        _recalcular_vencimientos(db, ticket)

    if payload.tags is not None:
        ticket.tags = payload.tags

    if payload.support_level:
        _log_history(db, ticket_id, "escalation", old_support_level, payload.support_level, current_user_id)

    if dynamic_fields is not None:
        save_ticket_dynamic_fields(db, ticket_id, dynamic_fields)
        _log_history(db, ticket_id, "dynamic_fields", "updated", "updated", current_user_id)

    return {
        "refresh_profile": normalized_status in ESTADOS_DE_TICKET_RESUELTOS and bool(ticket.assigned_to_user_id),
        "reassigned": bool(payload.assigned_to_user_id and old_assigned_to and payload.assigned_to_user_id != old_assigned_to),
        "record_routing_outcome": normalized_status in ESTADOS_DE_TICKET_RESUELTOS,
    }


def cambiar_estado_por_automatismo(db: Session, ticket: Ticket, estado: str, *, actor=None,
                                   origen: str, resolucion: str | None = None,
                                   metadatos: dict | None = None) -> bool:
    """Cambio de estado hecho por un automatismo (IA, playbook, catalogo).

    Auditoria 2026-11-22 (A-SD11): la auto-resolucion con LLM, la del agente
    autonomo, la operacion «auto-resolver» y los pasos del catalogo escribian
    `ticket.status` a mano: sin historial, sin `resolved_at`, sin evaluar el
    SLA, sin encuesta y sin `audit_log`. Ahora pasan por `apply_ticket_update`
    (la misma via que el PATCH) y dejan una entrada de auditoria con su
    `origen`. Devuelve False si el ticket ya estaba en ese estado.
    """
    from app.schemas.service_desk import TicketUpdateIn
    from app.services.audit import audit_log

    antes = _norm_enum(ticket.status)
    destino = normalize_ticket_status(estado)
    if antes == destino:
        return False
    if resolucion is not None:
        ticket.resolution = resolucion
    apply_ticket_update(db, ticket, ticket.id, TicketUpdateIn(status=destino),
                        current_user_id=getattr(actor, "id", None),
                        old_assigned_to=ticket.assigned_to_user_id,
                        old_support_level=ticket.support_level)
    audit_log(db, actor, "UPDATE", "tickets", ticket.id, ticket.number,
              old_values={"status": antes}, new_values={"status": destino},
              metadata={"origen": origen, **(metadatos or {})})
    return True


def _exigir_contrato_uc(db: Session, contrato_id: str, org_id) -> None:
    """Un UC es un contrato de ALM activo, con plazo del proveedor y de la organizacion del ticket."""
    from app.models.alm import ALMContract

    c = db.get(ALMContract, contrato_id)
    ajeno = c is not None and c.organization_id not in (None, org_id)
    sin_plazo = (c.resolution_hours or 0) <= 0 and (c.response_hours or 0) <= 0 if c is not None else True
    if c is None or ajeno or not c.is_active or sin_plazo:
        raise error(422, "contrato_sin_uc")
