"""Service-desk enums — shared base for the service_desk model package."""
import enum


class TicketType(str, enum.Enum):
    incident = "incident"
    service_request = "service_request"
    change = "change"
    problem = "problem"
    question = "question"


class TicketStatus(str, enum.Enum):
    new = "new"
    assigned = "assigned"
    in_progress = "in_progress"
    pending_client = "pending_client"
    pending_third = "pending_third"
    resolved = "resolved"
    closed = "closed"
    cancelled = "cancelled"


# Grupos de estados de ticket (barrido «nada en duro» 2026-11). Antes, unas 50
# tuplas literales repartidas por los servicios. Son `str`, para usarlas igual
# en `Ticket.status.in_(...)` que contra `status.value`.
#: Resuelto, con o sin cierre formal.
ESTADOS_DE_TICKET_RESUELTOS = (TicketStatus.resolved.value, TicketStatus.closed.value)
#: Ya no esta abierto: resuelto, cerrado o cancelado.
ESTADOS_DE_TICKET_CERRADOS = ESTADOS_DE_TICKET_RESUELTOS + (TicketStatus.cancelled.value,)
#: Abierto: todo lo que no esta cerrado (incluye los dos «pendiente de»).
ESTADOS_DE_TICKET_ABIERTOS = tuple(s.value for s in TicketStatus if s.value not in ESTADOS_DE_TICKET_CERRADOS)
#: Esperando a otro (cliente o tercero).
ESTADOS_DE_TICKET_EN_ESPERA = (TicketStatus.pending_client.value, TicketStatus.pending_third.value)
#: En curso del lado del equipo: abierto y sin esperar a nadie.
ESTADOS_DE_TICKET_EN_CURSO = tuple(s for s in ESTADOS_DE_TICKET_ABIERTOS if s not in ESTADOS_DE_TICKET_EN_ESPERA)


class TicketPriority(str, enum.Enum):
    p1_critical = "p1_critical"
    p2_high = "p2_high"
    p3_medium = "p3_medium"
    p4_low = "p4_low"


#: Prioridades de mayor a menor (para recorrerlas en informes).
PRIORIDADES_DE_TICKET = tuple(p.value for p in TicketPriority)


class TicketUrgency(str, enum.Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


class TicketImpact(str, enum.Enum):
    enterprise = "enterprise"
    department = "department"
    user = "user"
    minimal = "minimal"


class SupportLevel(str, enum.Enum):
    l1 = "l1"
    l2 = "l2"
    l3 = "l3"


class SLAStatus(str, enum.Enum):
    ok = "ok"
    at_risk = "at_risk"
    breached = "breached"
    paused = "paused"


class CIType(str, enum.Enum):
    application = "application"
    server = "server"
    database = "database"
    network = "network"
    service = "service"
    module = "module"
    integration = "integration"
    virtual_machine = "virtual_machine"
    container = "container"
    cloud = "cloud"
    endpoint = "endpoint"
    storage = "storage"
    other = "other"


class CIStatus(str, enum.Enum):
    operational = "operational"
    degraded = "degraded"
    maintenance = "maintenance"
    retired = "retired"


class ProblemStatus(str, enum.Enum):
    open = "open"
    investigating = "investigating"
    known_error = "known_error"
    resolved = "resolved"
    closed = "closed"


#: Problema resuelto, con o sin cierre formal.
ESTADOS_DE_PROBLEMA_RESUELTOS = (ProblemStatus.resolved.value, ProblemStatus.closed.value)


class KBStatus(str, enum.Enum):
    draft = "draft"
    in_review = "in_review"   # enviado a revision; lo publica un revisor
    published = "published"
    archived = "archived"


class TicketLinkType(str, enum.Enum):
    relates_to   = "relates_to"
    duplicates   = "duplicates"
    caused_by    = "caused_by"
    blocks       = "blocks"
    child_of     = "child_of"


class SLAEventType(str, enum.Enum):
    paused        = "paused"
    resumed       = "resumed"
    breach_warn   = "breach_warn"    # SLA consumido >= SLA_PREDICTION_WARNING_PCT (0.70 por defecto)
    breached      = "breached"       # SLA roto
    met           = "met"            # SLA cumplido al cerrar


class CIRelationType(str, enum.Enum):
    depends_on   = "depends_on"     # A depende de B
    hosts        = "hosts"          # servidor aloja aplicación
    connects_to  = "connects_to"    # red
    backed_up_by = "backed_up_by"
    monitored_by = "monitored_by"
    part_of      = "part_of"


class ChangeType(str, enum.Enum):
    standard  = "standard"    # pre-aprobado, bajo riesgo, procedimiento documentado
    normal    = "normal"      # requiere CAB
    emergency = "emergency"   # ECAB, urgente


#: Estados de un modelo de cambio estandar (`StandardChangeModel.status`).
ESTADO_MODELO_PROPUESTO = "proposed"     # pendiente de aprobacion del CAB
ESTADO_MODELO_APROBADO = "approved"      # preaprobado: sus cambios no pasan por el CAB
ESTADO_MODELO_SUSPENDIDO = "suspended"   # por tasa de fallo o a mano: sus cambios van al CAB
ESTADO_MODELO_RETIRADO = "retired"       # baja
ESTADOS_DE_MODELO_ESTANDAR = (ESTADO_MODELO_PROPUESTO, ESTADO_MODELO_APROBADO,
                              ESTADO_MODELO_SUSPENDIDO, ESTADO_MODELO_RETIRADO)


class ChangeRisk(str, enum.Enum):
    low    = "low"
    medium = "medium"
    high   = "high"
    critical = "critical"


class ChangeStatus(str, enum.Enum):
    draft           = "draft"
    submitted       = "submitted"
    cab_review      = "cab_review"      # pendiente aprobación CAB
    approved        = "approved"
    scheduled       = "scheduled"
    in_progress     = "in_progress"
    implemented     = "implemented"
    post_review     = "post_review"     # PIR: Post-Implementation Review
    closed_success  = "closed_success"
    closed_failed   = "closed_failed"
    cancelled       = "cancelled"


#: Maquina de estados de los cambios ITSM (auditoria 2026-11-22, C-SD3).
#: Origen → destinos permitidos. `approved` no es destino de nadie: solo lo
#: escriben el CAB (`cab_workflow_service`), la decision de un administrador
#: (`change_service.approve_change_request`) y la auto-aprobacion de un
#: estandar de bajo riesgo. Antes se admitia `draft → in_progress →
#: closed_success` con un PATCH, saltandose el comite.
TRANSICIONES_DE_CAMBIO: dict[str, frozenset] = {
    ChangeStatus.draft.value: frozenset({ChangeStatus.submitted.value, ChangeStatus.cab_review.value,
                                         ChangeStatus.cancelled.value}),
    ChangeStatus.submitted.value: frozenset({ChangeStatus.cab_review.value, ChangeStatus.draft.value,
                                             ChangeStatus.cancelled.value}),
    # Sin vuelta a borrador desde la revision: reiniciar el CAB borraba los
    # votos en contra (A-SD19). Un cambio rechazado se cancela y se rehace.
    ChangeStatus.cab_review.value: frozenset({ChangeStatus.cancelled.value}),
    ChangeStatus.approved.value: frozenset({ChangeStatus.scheduled.value, ChangeStatus.in_progress.value,
                                            ChangeStatus.cancelled.value}),
    ChangeStatus.scheduled.value: frozenset({ChangeStatus.in_progress.value, ChangeStatus.cancelled.value}),
    ChangeStatus.in_progress.value: frozenset({ChangeStatus.implemented.value,
                                               ChangeStatus.closed_failed.value}),
    ChangeStatus.implemented.value: frozenset({ChangeStatus.post_review.value, ChangeStatus.closed_success.value,
                                               ChangeStatus.closed_failed.value}),
    ChangeStatus.post_review.value: frozenset({ChangeStatus.closed_success.value,
                                               ChangeStatus.closed_failed.value}),
    ChangeStatus.closed_success.value: frozenset(),
    ChangeStatus.closed_failed.value: frozenset(),
    ChangeStatus.cancelled.value: frozenset(),
}

#: Estados desde los que se puede arrancar la implantacion (o un despliegue).
ESTADOS_DE_CAMBIO_IMPLANTABLES = frozenset({ChangeStatus.approved.value, ChangeStatus.scheduled.value})


class MajorIncidentStatus(str, enum.Enum):
    active   = "active"
    resolved = "resolved"
    closed   = "closed"


#: Incidente mayor resuelto, con o sin cierre formal.
ESTADOS_DE_INCIDENTE_MAYOR_RESUELTOS = (MajorIncidentStatus.resolved.value, MajorIncidentStatus.closed.value)


class OnCallRotationType(str, enum.Enum):
    weekly   = "weekly"    # cada semana rota el agente
    daily    = "daily"     # cada día rota
    custom   = "custom"    # intervalos definidos manualmente


class EscalationTrigger(str, enum.Enum):
    sla_at_risk   = "sla_at_risk"    # SLA en riesgo (SLA_PREDICTION_WARNING_PCT, 0.70 por defecto)
    sla_breached  = "sla_breached"   # SLA roto
    idle_hours    = "idle_hours"     # Sin actividad N horas
    priority      = "priority"       # Prioridad específica sin asignar
    reopened      = "reopened"       # Ticket reabierto


class EscalationAction(str, enum.Enum):
    notify_manager    = "notify_manager"     # notificar al jefe del agente
    notify_group_lead = "notify_group_lead"  # notificar al lead del grupo
    reassign_group    = "reassign_group"     # mover a otro grupo
    elevate_priority  = "elevate_priority"   # subir prioridad
    notify_custom     = "notify_custom"      # enviar a lista custom


class StatusPageComponentStatus(str, enum.Enum):
    operational          = "operational"
    degraded_performance = "degraded_performance"
    partial_outage       = "partial_outage"
    major_outage         = "major_outage"
    maintenance          = "maintenance"
