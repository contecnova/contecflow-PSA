
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.client_portal import ClientUser
from app.models.service_desk import ServiceItem, Ticket
from app.schemas.service_desk import TicketCreateIn
from app.services.service_desk.routing_rule_service import apply_routing_rules
from app.services.service_desk.scoping import resolve_sla_policy_for_ticket as _resolve_sla_policy_for_ticket
from app.services.service_desk.dynamic_ticket_fields_service import save_ticket_dynamic_fields
from app.services.sla_service import (
    PRIORITY_MATRIX,
    calculate_sla_due as _calculate_sla_due,
    next_ticket_number as _next_ticket_number,
    norm_enum as _norm_enum,
)
import logging

logger = logging.getLogger(__name__)


def _emit_ticket_created_metric(ticket: Ticket) -> None:
    """Best-effort Prometheus counter increment; never raises into business flow."""
    try:
        from app.core.metrics import tickets_created_total

        def _v(field):
            value = getattr(ticket, field, None)
            return getattr(value, "value", value) if value is not None else "unknown"

        tickets_created_total.labels(
            tenant_id=str(getattr(ticket, "organization_id", None) or "unknown"),
            ticket_type=str(_v("ticket_type")),
            priority=str(_v("priority")),
            source=str(_v("source")),
        ).inc()
    except Exception:
        logger.debug("_v: fallo best-effort ignorado", exc_info=True)


def _semantic_assignee_if_enabled(db: Session, ticket: Ticket, candidate_user_ids: list[str]) -> str | None:
    """Return semantic suggestion when enabled by SemConfig; else None.

    This preserves semantic engine value without replacing the ML routing fallback.
    """
    try:
        from app.models.semantic_engine import SemConfig
        from app.services.semantic_classifier import SemanticAssigner

        cfg = db.query(SemConfig).first()
        if not cfg or not bool(getattr(cfg, "auto_assign_tickets", False)):
            return None

        priority = str(ticket.priority.value) if hasattr(ticket.priority, "value") else str(ticket.priority or "medium")
        suggestion = SemanticAssigner(db).suggest_for_ticket(
            ticket.title or "",
            ticket.description or "",
            candidate_user_ids,
            priority=priority,
        )
        suggested = suggestion.get("suggested_user_id")
        if suggested and suggested in set(candidate_user_ids):
            return suggested
    except Exception:
        return None
    return None


# ── Asignación automática de un ticket nuevo ─────────────────────────────────
#
# Auditoria 2026-08 (hallazgo 18). `_auto_assign_ticket_on_create` era
# complejidad 18 y decide A QUIEN se asigna cada ticket que entra. Un error aqui
# manda el trabajo al agente equivocado sin que nada falle.
#
# Al partirla aparecio que el BLOQUE DE CIERRE estaba escrito dos veces,
# literalmente: normalizar el estado a «asignado», hacer `flush` si el ticket
# todavia no tiene id, y registrar el evento de enrutado. Los dos caminos
# —asignacion manual previa y asignacion automatica— terminan igual, asi que
# ahora terminan en la misma funcion.


def _valor_de_estado(v) -> str:
    """El estado como cadena, venga como Enum, como texto o como nombre completo.

    El tercer caso (`"TicketStatus.new"`) existe porque hay filas guardadas con
    la representacion del Enum en vez de su valor.
    """
    if hasattr(v, "value"):
        return str(v.value)
    s = str(v)
    if s.startswith("TicketStatus."):
        return s.split(".", 1)[1]
    return s


def _finalizar_asignacion(db: Session, ticket: Ticket) -> None:
    """Cierra la asignacion: estado, `flush` si hace falta, y evento de enrutado.

    Es el bloque que estaba duplicado en los dos caminos. El `flush` va antes
    del evento porque `record_routing_event` necesita el id del ticket, y un
    ticket recien construido todavia no lo tiene.
    """
    from app.models.service_desk import TicketStatus

    estado = _valor_de_estado(ticket.status)
    # `"None"` en el conjunto no es redundante con `not ticket.status`: cubre las
    # filas donde el estado se guardo como la CADENA "None", que es truthy y por
    # tanto no la caza la primera condicion.
    if not ticket.status or estado in {
        TicketStatus.new.value, TicketStatus.assigned.value, "None",
    }:
        ticket.status = TicketStatus.assigned

    if not ticket.id:
        db.flush()

    from app.services.service_desk.ml_routing_service import record_routing_event
    record_routing_event(db, ticket)


def _candidatos_de_asignacion(db: Session, ticket: Ticket) -> list:
    """Los agentes elegibles para este ticket.

    Si hay grupo, sus miembros. Si no, TODOS los agentes del service desk,
    deduplicados por usuario: una persona en tres grupos apareceria tres veces y
    el modelo de enrutado la ponderaria el triple.
    """
    from app.models.service_desk import AgentGroupMember

    if ticket.assigned_group_id:
        return (
            db.query(AgentGroupMember)
            .filter(AgentGroupMember.group_id == ticket.assigned_group_id)
            .all()
        )

    vistos: set[str] = set()
    miembros = []
    for m in db.query(AgentGroupMember).all():
        if m.user_id in vistos:
            continue
        vistos.add(m.user_id)
        miembros.append(m)
    return miembros


def _elegir_agente(db: Session, ticket: Ticket, miembros: list):
    """El agente elegido, o None si no se puede decidir.

    Se intenta primero el clasificador semantico y despues el modelo de
    enrutado. El orden importa: el semantico mira el CONTENIDO del ticket y solo
    responde cuando esta habilitado y seguro, asi que cuando responde es la
    respuesta mejor informada.
    """
    from app.services.service_desk.ml_routing_service import predict_best_agent

    candidatos = [m.user_id for m in miembros if getattr(m, "user_id", None)]
    return (
        _semantic_assignee_if_enabled(db, ticket, candidatos)
        or predict_best_agent(db, ticket, miembros)
    )


def _auto_assign_ticket_on_create(db: Session, ticket: Ticket) -> None:
    """Ensure every newly created ticket gets an assignee using ML routing.

    If a manual assignee already exists, preserve it and just normalize status/event.
    """
    # Una asignacion manual manda: no se reemplaza nunca por la automatica.
    if ticket.assigned_to_user_id:
        _finalizar_asignacion(db, ticket)
        return

    # El catalogo de servicios puede fijar el grupo destino del tipo de peticion.
    if (not ticket.assigned_group_id and ticket.service_item
            and ticket.service_item.auto_assign_group):
        ticket.assigned_group_id = ticket.service_item.auto_assign_group

    miembros = _candidatos_de_asignacion(db, ticket)
    if not miembros:
        # Sin agentes no se inventa un destinatario: el ticket queda sin asignar
        # y visible en la cola, que es preferible a asignarlo a nadie.
        return

    elegido = _elegir_agente(db, ticket, miembros)
    if not elegido:
        return

    ticket.assigned_to_user_id = elegido
    if not ticket.assigned_group_id:
        # Se hereda el grupo del agente elegido para que el ticket quede en una
        # cola y no suelto.
        origen = next((m for m in miembros if m.user_id == elegido), None)
        if origen:
            ticket.assigned_group_id = origen.group_id

    _finalizar_asignacion(db, ticket)


def _vencimientos(db: Session, priority, sla_policy, service_item) -> tuple:
    """Vencimientos de respuesta y resolución en el calendario de la política.

    Un servicio del catálogo declara sus propias horas y manda sobre las de la
    prioridad; antes esas horas se sumaban como reloj de pared, saltándose la
    jornada, los días laborables y los festivos.
    """
    horas = None
    if service_item is not None and service_item.sla_response_hours and service_item.sla_resolution_hours:
        horas = (service_item.sla_response_hours, service_item.sla_resolution_hours)
    return _calculate_sla_due(
        priority, sla_policy, db=db,
        org_id=db.info.get("organization_id"), hours=horas,
    )


def build_internal_ticket(db: Session, payload: TicketCreateIn, requester_user_id: str) -> Ticket:
    priority = payload.priority
    if not priority:
        priority = PRIORITY_MATRIX.get(
            (_norm_enum(payload.urgency), _norm_enum(payload.impact)),
            "p3_medium",
        )

    sla_policy = _resolve_sla_policy_for_ticket(
        db,
        contract_id=payload.contract_id,
        client_id=payload.client_id,
    )

    service_item = None
    if payload.service_item_id:
        service_item = db.query(ServiceItem).filter(ServiceItem.id == payload.service_item_id).first()
        if service_item and not payload.priority:
            priority = (
                service_item.default_priority.value
                if hasattr(service_item.default_priority, "value")
                else service_item.default_priority
            )
    resp_due, res_due = _vencimientos(db, priority, sla_policy, service_item)

    ticket = Ticket(
        number=_next_ticket_number(payload.ticket_type, db),
        ticket_type=payload.ticket_type,
        title=payload.title,
        description=payload.description,
        urgency=payload.urgency,
        impact=payload.impact,
        priority=priority,
        support_level=(
            service_item.default_support_level.value
            if service_item and hasattr(service_item.default_support_level, "value")
            else "l1"
        ),
        project_id=payload.project_id,
        client_id=payload.client_id,
        contract_id=payload.contract_id,
        ci_id=payload.ci_id,
        service_item_id=payload.service_item_id,
        assigned_to_user_id=payload.assigned_to_user_id,
        assigned_group_id=payload.assigned_group_id,
        requester_user_id=requester_user_id,
        requester_name=payload.requester_name,
        requester_email=payload.requester_email,
        tags=payload.tags,
        source=payload.source,
        sla_policy_id=sla_policy.id if sla_policy else None,
        sla_response_due=resp_due,
        sla_resolution_due=res_due,
        created_by_user_id=requester_user_id,
    )

    db.add(ticket)
    apply_routing_rules(ticket, db)
    _auto_assign_ticket_on_create(db, ticket)
    db.flush()
    save_ticket_dynamic_fields(db, ticket.id, payload.dynamic_fields)
    _emit_ticket_created_metric(ticket)
    return ticket


def build_client_portal_ticket(db: Session, payload: TicketCreateIn, client: ClientUser) -> Ticket:
    priority = payload.priority
    if not priority:
        priority = PRIORITY_MATRIX.get(
            (_norm_enum(payload.urgency), _norm_enum(payload.impact)),
            "p3_medium",
        )

    sla_policy = _resolve_sla_policy_for_ticket(
        db,
        contract_id=payload.contract_id,
        client_id=client.client_org_id,
    )
    service_item = None
    if payload.service_item_id:
        service_item = db.query(ServiceItem).filter(ServiceItem.id == payload.service_item_id).first()
    resp_due, res_due = _vencimientos(db, priority, sla_policy, service_item)

    if payload.project_id and payload.project_id != client.project_id:
        raise HTTPException(403, "No puedes crear tickets para proyectos a los que no perteneces")

    ticket = Ticket(
        number=_next_ticket_number(payload.ticket_type, db),
        ticket_type=payload.ticket_type,
        title=payload.title,
        description=payload.description,
        urgency=payload.urgency,
        impact=payload.impact,
        priority=priority,
        project_id=client.project_id,
        client_id=client.client_org_id,
        contract_id=payload.contract_id,
        ci_id=payload.ci_id,
        service_item_id=payload.service_item_id,
        tags=payload.tags,
        requester_client_id=client.id,
        source="portal",
        sla_policy_id=sla_policy.id if sla_policy else None,
        sla_response_due=resp_due,
        sla_resolution_due=res_due,
    )
    db.add(ticket)
    apply_routing_rules(ticket, db)
    _auto_assign_ticket_on_create(db, ticket)
    db.flush()
    save_ticket_dynamic_fields(db, ticket.id, payload.dynamic_fields)
    _emit_ticket_created_metric(ticket)
    return ticket


def build_channel_ticket(
    db: Session,
    *,
    org_id,
    titulo: str,
    descripcion: str,
    source: str,
    requester_user=None,
    requester_client: ClientUser | None = None,
    requester_name: str | None = None,
    requester_email: str | None = None,
    requester_phone: str | None = None,
) -> Ticket:
    """Ticket que llega por un canal (correo, SMS...), con las mismas reglas que el resto.

    Auditoria 2026-11: el correo entrante montaba su ticket a mano —numero
    `EML-xxxx` fuera de la numeracion, el primer administrador como agente,
    sin organizacion— y se saltaba el enrutado y la asignacion automatica.
    El tipo sale de `SD_CHANNEL_TICKET_TYPE` y la prioridad de la matriz de
    urgencia e impacto, con los valores medios: el remitente no los declara.
    """
    from app.models.service_desk import TicketImpact, TicketType, TicketUrgency
    from app.services import settings_service as _ss

    try:
        tipo = TicketType(_ss.get_runtime_str(db, "SD_CHANNEL_TICKET_TYPE", org_id) or "incident")
    except ValueError:
        logger.warning("SD_CHANNEL_TICKET_TYPE inválido; se usa incident")
        tipo = TicketType.incident
    priority = PRIORITY_MATRIX[(TicketUrgency.medium.value, TicketImpact.user.value)]
    client_id = requester_client.client_org_id if requester_client is not None else None
    sla_policy = _resolve_sla_policy_for_ticket(db, client_id=client_id)
    resp_due, res_due = _calculate_sla_due(priority, sla_policy, db=db, org_id=org_id)
    ticket = Ticket(
        organization_id=org_id,
        number=_next_ticket_number(tipo.value, db, org_id),
        ticket_type=tipo,
        title=titulo,
        description=descripcion,
        urgency=TicketUrgency.medium,
        impact=TicketImpact.user,
        priority=priority,
        source=source,
        client_id=client_id,
        project_id=requester_client.project_id if requester_client is not None else None,
        requester_user_id=requester_user.id if requester_user is not None else None,
        requester_client_id=requester_client.id if requester_client is not None else None,
        requester_name=requester_name,
        requester_email=requester_email,
        requester_phone=requester_phone,
        sla_policy_id=sla_policy.id if sla_policy else None,
        sla_response_due=resp_due,
        sla_resolution_due=res_due,
    )
    db.add(ticket)
    apply_routing_rules(ticket, db)
    _auto_assign_ticket_on_create(db, ticket)
    db.flush()
    _emit_ticket_created_metric(ticket)
    return ticket
