
from sqlalchemy.orm import Session

from app.models.client_portal import ClientUser
from app.models.service_desk import ServiceItem, SupportLevel, Ticket, TicketPriority
from app.schemas.service_desk import TicketCreateIn
from app.services.service_desk.routing_rule_service import apply_routing_rules
from app.services.service_desk.scoping import resolve_sla_policy_for_ticket as _resolve_sla_policy_for_ticket
from app.services.service_desk.dynamic_ticket_fields_service import save_ticket_dynamic_fields
from app.services.service_desk.catalog_approval_service import (
    solicitar_si_hace_falta as solicitar_aprobacion_si_hace_falta,
)
from app.services.sla_service import (
    PRIORITY_MATRIX,
    calculate_sla_due as _calculate_sla_due,
    next_ticket_number as _next_ticket_number,
    norm_enum as _norm_enum,
)
import logging
from app.core.codigos_de_error import error as error_con_codigo

logger = logging.getLogger(__name__)


def _emit_ticket_created_metric(ticket: Ticket) -> None:
    """Best-effort Prometheus counter increment; never raises into business flow."""
    try:
        from app.core.metrics import tickets_created_total

        def _v(field):
            value = getattr(ticket, field, None)
            return getattr(value, "value", value) if value is not None else "unknown"

        from app.core.metricas_empresa import etiqueta_de_empresa
        # 22-11-2026: etiqueta de empresa acotada (antes el id crudo: una serie por empresa sin tope).
        tickets_created_total.labels(
            tenant_id=etiqueta_de_empresa(getattr(ticket, "organization_id", None)),
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
            # 23-11-2026: se registra (pendiente) en `_finalizar_asignacion`, ya con id.
            ticket._sugerencia_semantica = suggestion
            return suggested
    except Exception:
        logger.warning("_semantic_assignee_if_enabled: excepcion ignorada", exc_info=True)
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
    _registrar_sugerencia_semantica(db, ticket)


def _registrar_sugerencia_semantica(db: Session, ticket: Ticket) -> None:
    """La IA eligió al agente: `SemAssignment` pendiente (23-11-2026). No confirma.

    Se confirma si ese agente lo resuelve y se rechaza si se reasigna
    (`semantic_engine_service`). Antes los tickets no dejaban rastro y la
    precisión del motor solo contaba tareas.
    """
    sugerencia = getattr(ticket, "_sugerencia_semantica", None)
    if not sugerencia or ticket.assigned_to_user_id != sugerencia.get("suggested_user_id"):
        return
    try:
        from app.services.semantic_engine_service import registrar_sugerencia_automatica
        registrar_sugerencia_automatica(db, item_type="ticket", item_id=ticket.id, item_title=ticket.title,
                                        sugerencia=sugerencia)
    except Exception:
        logger.warning("No se pudo registrar la sugerencia de la IA del ticket %s", ticket.id, exc_info=True)


def _candidatos_de_asignacion(db: Session, ticket: Ticket) -> list:
    """Los agentes elegibles para este ticket.

    Si hay grupo, sus miembros. Si no, TODOS los agentes del service desk,
    deduplicados por usuario: una persona en tres grupos apareceria tres veces y
    el modelo de enrutado la ponderaria el triple.
    """
    from app.models.service_desk import AgentGroup, AgentGroupMember

    # Auditoria 2026-11-22 (A-SD5): sin empresa (buzon o secreto de correo
    # global, Slack sin vincular, worker) `query(AgentGroupMember).all()`
    # devolvia los agentes de TODAS las empresas. Ahora solo los de los grupos
    # de la empresa del ticket; sin empresa, nadie (queda en la cola).
    org_id = ticket.organization_id or db.info.get("organization_id")
    if not org_id:
        return []
    base = (db.query(AgentGroupMember)
            .join(AgentGroup, AgentGroup.id == AgentGroupMember.group_id)
            .filter(AgentGroup.organization_id == org_id))
    if ticket.assigned_group_id:
        return base.filter(AgentGroupMember.group_id == ticket.assigned_group_id).all()

    vistos: set[str] = set()
    miembros = []
    for m in base.all():
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


def _vencimientos(db: Session, priority, sla_policy, service_item, org_id=None) -> tuple:
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
        org_id=org_id or db.info.get("organization_id"), hours=horas,
    )


def _enrutar(db: Session, ticket: Ticket, prioridad_inicial, sla_policy, service_item) -> None:
    """Reglas de enrutado y, si cambian la prioridad, vencimientos de nuevo.

    Auditoria 2026-11-22 (A-SD4): la accion `set_priority` cambiaba la
    prioridad despues de calcular los vencimientos, y el ticket vencia con los
    plazos de la prioridad anterior (un P1 enrutado vencia como P3).
    """
    apply_routing_rules(ticket, db)
    nueva = _norm_enum(ticket.priority)
    if nueva != _norm_enum(prioridad_inicial):
        ticket.sla_response_due, ticket.sla_resolution_due = _vencimientos(
            db, nueva, sla_policy, service_item, ticket.organization_id)


def _aplicar_regla_sla(db: Session, ticket: Ticket) -> None:
    """Al abrir (mejoras de mercado 16-11-2026): la regla de SLA de la empresa
    que encaje fija los plazos (`reglas_sla`) y, si el tipo tiene ciclo de
    vida propio, el ticket nace en su estado inicial (`ciclos_de_vida`)."""
    from app.services.service_desk.ciclos_de_vida import estado_inicial
    from app.services.service_desk.reglas_sla import aplicar_regla
    aplicar_regla(db, ticket)
    ticket.lifecycle_state = estado_inicial(db, ticket)


def _solicitante_externo(db: Session, payload: TicketCreateIn, agente_id: str) -> dict:
    """Quien pide el ticket cuando el agente lo abre en su nombre.

    Auditoria 2026-11: el formulario no dejaba indicar al solicitante y se
    guardaba siempre al agente: en un ticket abierto por telefono el cliente no
    recibia ningun aviso. Con un correo, el solicitante es esa persona: su
    usuario del portal si lo tiene (asi lo ve tambien alli), o un usuario
    interno; si no, queda el nombre y el correo.
    """
    from sqlalchemy import func
    from app.models.user import User

    correo = (payload.requester_email or "").strip().lower()
    if not correo:
        return {"requester_user_id": agente_id}
    cliente = db.query(ClientUser).filter(func.lower(ClientUser.email) == correo,
                                          ClientUser.is_active == True).first()  # noqa: E712
    if cliente is not None:
        return {"requester_user_id": None, "requester_client_id": cliente.id}
    usuario = db.query(User).filter(func.lower(User.email) == correo, User.is_active == True).first()  # noqa: E712
    return {"requester_user_id": usuario.id if usuario else None}


def build_internal_ticket(db: Session, payload: TicketCreateIn, requester_user_id: str) -> Ticket:
    priority = payload.priority
    if not priority:
        priority = PRIORITY_MATRIX.get(
            (_norm_enum(payload.urgency), _norm_enum(payload.impact)),
            TicketPriority.p3_medium.value,
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
            else SupportLevel.l1.value
        ),
        project_id=payload.project_id,
        client_id=payload.client_id,
        contract_id=payload.contract_id,
        ci_id=payload.ci_id,
        service_item_id=payload.service_item_id,
        assigned_to_user_id=payload.assigned_to_user_id,
        assigned_group_id=payload.assigned_group_id,
        **_solicitante_externo(db, payload, requester_user_id),
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
    _enrutar(db, ticket, priority, sla_policy, service_item)
    _auto_assign_ticket_on_create(db, ticket)
    db.flush()
    save_ticket_dynamic_fields(db, ticket.id, payload.dynamic_fields)
    _aplicar_regla_sla(db, ticket)
    if solicitar_aprobacion_si_hace_falta(db, ticket, service_item) is None:
        from app.services.service_desk.fulfillment_service import crear_tareas
        crear_tareas(db, ticket, service_item)
    _emit_ticket_created_metric(ticket)
    return ticket


def _validar_referencias_del_portal(db: Session, payload: TicketCreateIn, client: ClientUser) -> None:
    """Contrato y CI que cuelga un cliente del portal: solo los suyos.

    Auditoria 2026-11-22 (servicios m-z, 4.3): se guardaban tal cual, asi que
    un cliente podia colgar el contrato (y su politica de SLA) o un CI de otro
    cliente o de otra empresa. El contrato ha de ser de su cliente y su
    empresa; el CI, de su empresa y de su proyecto. Lo ajeno responde igual que
    lo inexistente (404).
    """
    org = getattr(client, "organization_id", None)
    if payload.contract_id:
        from app.models.pipeline import Contract
        contrato = db.query(Contract).filter(Contract.id == payload.contract_id).first()
        if (contrato is None or not client.client_org_id or contrato.client_id != client.client_org_id
                or (org and contrato.organization_id not in (None, org))):
            raise error_con_codigo(404, "no_encontrado", detail="Contrato no encontrado", que="contrato")
    if payload.ci_id:
        from app.models.service_desk import ConfigurationItem
        ci = db.query(ConfigurationItem).filter(ConfigurationItem.id == payload.ci_id).first()
        if (ci is None or not client.project_id or ci.project_id != client.project_id
                or (org and ci.organization_id not in (None, org))):
            raise error_con_codigo(404, "no_encontrado", detail="CI no encontrado", que="ci")


def build_client_portal_ticket(db: Session, payload: TicketCreateIn, client: ClientUser) -> Ticket:
    _validar_referencias_del_portal(db, payload, client)
    priority = payload.priority
    if not priority:
        priority = PRIORITY_MATRIX.get(
            (_norm_enum(payload.urgency), _norm_enum(payload.impact)),
            TicketPriority.p3_medium.value,
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
        raise error_con_codigo(403, "ticket_proyecto_ajeno")

    ticket = Ticket(
        number=_next_ticket_number(payload.ticket_type, db),
        ticket_type=payload.ticket_type,
        title=payload.title,
        description=payload.description,
        urgency=payload.urgency,
        impact=payload.impact,
        priority=priority,
        project_id=client.project_id,
        # Auditoria 2026-11: el ticket del portal quedaba sin organizacion y no
        # contaba en el panel del cliente (ni en el de la organizacion).
        organization_id=getattr(client, "organization_id", None),
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
    _enrutar(db, ticket, priority, sla_policy, service_item)
    _auto_assign_ticket_on_create(db, ticket)
    db.flush()
    save_ticket_dynamic_fields(db, ticket.id, payload.dynamic_fields)
    _aplicar_regla_sla(db, ticket)
    if solicitar_aprobacion_si_hace_falta(db, ticket, service_item) is None:
        from app.services.service_desk.fulfillment_service import crear_tareas
        crear_tareas(db, ticket, service_item)
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
    priority: str | None = None,
    ticket_type: str | None = None,
    ci_id: str | None = None,
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
        tipo = TicketType(ticket_type or _ss.get_runtime_str(db, "SD_CHANNEL_TICKET_TYPE", org_id) or "incident")
    except ValueError:
        logger.warning("SD_CHANNEL_TICKET_TYPE inválido; se usa incident")
        tipo = TicketType.incident
    priority = priority or PRIORITY_MATRIX[(TicketUrgency.medium.value, TicketImpact.user.value)]
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
        ci_id=ci_id,
        sla_policy_id=sla_policy.id if sla_policy else None,
        sla_response_due=resp_due,
        sla_resolution_due=res_due,
    )
    db.add(ticket)
    _enrutar(db, ticket, priority, sla_policy, None)
    _auto_assign_ticket_on_create(db, ticket)
    db.flush()
    _aplicar_regla_sla(db, ticket)
    _emit_ticket_created_metric(ticket)
    return ticket


def build_fulfillment_task(db: Session, peticion: Ticket, titulo: str, group_id: str, tarea=None) -> Ticket:
    """Una tarea de cumplimiento: ticket hijo de la peticion, en la cola indicada.

    Hereda solicitante, cliente, organizacion y politica de SLA de la peticion;
    la cola es la de la tarea y el agente lo elige la asignacion automatica
    dentro de ella. Con `tarea` (fila de `sd_service_item_tasks`, mejoras de
    mercado 16-11-2026): su persona, su descripcion y su SLA propio, en el
    calendario de la politica de la peticion.
    """
    from app.models.service_desk import ServiceItem, SLAPolicy, TicketType
    from app.services.service_desk.fulfillment_service import ORIGEN

    definicion = tarea
    politica = db.get(SLAPolicy, peticion.sla_policy_id) if peticion.sla_policy_id else None
    prioridad = getattr(peticion.priority, "value", peticion.priority)
    item = db.get(ServiceItem, peticion.service_item_id) if peticion.service_item_id else None
    resp_due, res_due = _vencimientos(db, prioridad, politica, item)
    if definicion is not None and definicion.sla_hours:
        horas = float(definicion.sla_hours)
        horas_resp = min(float(item.sla_response_hours or horas), horas) if item is not None else horas
        resp_due, res_due = _calculate_sla_due(prioridad, politica, db=db, org_id=db.info.get("organization_id"),
                                               hours=(horas_resp, horas))
    extra = f"{definicion.description}\n\n" if definicion is not None and definicion.description else ""
    tarea = Ticket(
        organization_id=peticion.organization_id,
        number=_next_ticket_number(TicketType.service_request.value, db, peticion.organization_id),
        ticket_type=TicketType.service_request,
        title=f"{peticion.number} · {titulo}"[:500],
        description=f"Tarea de la petición {peticion.number}: {peticion.title}\n\n{extra}{peticion.description}",
        fulfillment_task_id=definicion.id if definicion is not None else None,
        assigned_to_user_id=definicion.assignee_user_id if definicion is not None else None,
        priority=prioridad, urgency=peticion.urgency, impact=peticion.impact,
        source=ORIGEN, parent_ticket_id=peticion.id, assigned_group_id=group_id,
        requester_user_id=peticion.requester_user_id, requester_client_id=peticion.requester_client_id,
        requester_name=peticion.requester_name, requester_email=peticion.requester_email,
        client_id=peticion.client_id, project_id=peticion.project_id, service_item_id=peticion.service_item_id,
        sla_policy_id=peticion.sla_policy_id, sla_response_due=resp_due, sla_resolution_due=res_due,
        created_by_user_id=peticion.created_by_user_id,
    )
    db.add(tarea)
    if tarea.assigned_to_user_id is None:
        _auto_assign_ticket_on_create(db, tarea)
    db.flush()
    return tarea


def acotar_alta_del_externo(db: Session, payload: TicketCreateIn, user) -> None:
    """Externos como internos (16-11-2026): el subcontratado abre tickets como un
    agente, pero solo de lo suyo. El ticket queda en su alcance
    (`created_by_user_id`); lo que se le cuelga tambien ha de estarlo:

    - el proyecto, uno de los suyos (`scope_projects_query`); si no, 404;
    - cliente y contrato (datos comerciales), solo los del proyecto;
    - el CI (CMDB de la empresa), no;
    - el asignado, alguien que ve (`ids_de_personas_visibles`).
    """
    from app.services.politica_de_visibilidad import es_externo, ids_de_personas_visibles
    if not es_externo(user):
        return
    from app.models.pipeline import Contract
    from app.models.project import Project
    from app.services.project_service import scope_projects_query
    proyecto = None
    if payload.project_id:
        proyecto = scope_projects_query(db.query(Project), db, user).filter(Project.id == payload.project_id).first()
        if proyecto is None:
            raise error_con_codigo(404, "no_encontrado", detail="Proyecto no encontrado", que="proyecto")
    cliente_del_proyecto = getattr(proyecto, "client_id", None)
    if payload.client_id and payload.client_id != cliente_del_proyecto:
        raise error_con_codigo(404, "no_encontrado", detail="Cliente no encontrado", que="cliente")
    if payload.contract_id:
        contrato = db.query(Contract).filter(Contract.id == payload.contract_id).first()
        if contrato is None or not cliente_del_proyecto or getattr(contrato, "client_id", None) != cliente_del_proyecto:
            raise error_con_codigo(404, "no_encontrado", detail="Contrato no encontrado", que="contrato")
    if payload.ci_id:
        raise error_con_codigo(403, "cmdb_no_disponible_rol")
    if payload.assigned_to_user_id and payload.assigned_to_user_id not in ids_de_personas_visibles(db, user):
        raise error_con_codigo(404, "no_encontrado", detail="Usuario no encontrado", que="usuario")
