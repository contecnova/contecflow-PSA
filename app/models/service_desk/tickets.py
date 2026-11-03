"""service_desk.tickets models — split from the former 1385-LOC god-file."""

from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Text, Boolean, Integer, Enum, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import false as sa_false, func
import uuid
from app.db.base import Base


from app.models.service_desk._enums import SLAStatus, SupportLevel, TicketImpact, TicketLinkType, TicketPriority, TicketStatus, TicketType, TicketUrgency

class Ticket(Base):
    __tablename__ = "sd_tickets"
    # El numero es unico dentro de la organizacion: cada cliente tiene su
    # INC-0001. Unico en toda la base, la segunda organizacion chocaba con la
    # primera en cuanto coincidian numeros.
    __table_args__ = (UniqueConstraint("organization_id", "number", name="uq_sd_tickets_org_number"),)

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    number = Column(String(20), nullable=False, index=True)

    ticket_type = Column(Enum(TicketType), nullable=False, index=True)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=False)

    status = Column(Enum(TicketStatus), default=TicketStatus.new, nullable=False, index=True)
    priority = Column(Enum(TicketPriority), default=TicketPriority.p3_medium, nullable=False, index=True)
    urgency = Column(Enum(TicketUrgency), default=TicketUrgency.medium)
    impact = Column(Enum(TicketImpact), default=TicketImpact.user)
    support_level = Column(Enum(SupportLevel), default=SupportLevel.l1)

    requester_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    requester_client_id = Column(String(36), ForeignKey("client_users.id"), nullable=True)
    requester_name = Column(String(255), nullable=True)
    # Auditoria 2026-09. Esta columna no existia y el servicio de SMS entrantes
    # la pasaba igual —detras de un `hasattr` que protegia el valor y no la
    # palabra clave—, asi que **crear un ticket desde un SMS reventaba
    # siempre** con `TypeError`. El telefono se guardaba de rebote en
    # `requester_name` y en la descripcion.
    #
    # Se anade como campo propio porque en un ticket abierto por SMS el
    # telefono **es** la identidad de quien lo abre: sin el no hay a quien
    # responder. Nullable, porque los tickets que no vienen por SMS no lo
    # tienen. 32 caracteres dan para un E.164 con extension.
    requester_phone = Column(String(32), nullable=True)
    # Auditoria 2026-09. Enlace a la incidencia mayor que agrupa este ticket.
    #
    # La decision de diseno que faltaba, dicha en voz alta: **un ticket
    # pertenece como mucho a UNA incidencia mayor**, y una incidencia mayor
    # agrupa muchos tickets. Es el modelo de ITIL y es el conservador — una
    # tabla de union permitiria que dos incidencias mayores compartieran
    # tickets, y eso hay que quererlo explicitamente, no heredarlo de una
    # eleccion tecnica.
    #
    # Sin esta columna, la comprobacion de cumplimiento «P1 sin incidencia
    # mayor declarada» estaba declarada **no evaluable**: el codigo preguntaba
    # por `MajorIncident.tickets` detras de un `hasattr` correcto sobre una
    # relacion inexistente, asi que o saltaba en todos los P1 o en ninguno.
    major_incident_id = Column(
        String(36), ForeignKey("sd_major_incidents.id", ondelete="SET NULL"),
        nullable=True, index=True)
    requester_email = Column(String(255), nullable=True)

    assigned_to_user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    assigned_group_id = Column(String(36), ForeignKey("sd_agent_groups.id"), nullable=True)

    # Context – all optional, works without project
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True, index=True)
    # Empresa cliente directa (independiente del proyecto)
    client_id  = Column(String(36), ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True)
    # Tipo de recurso vinculado (proyecto, licencia, contrato, activo...)
    linked_resource_type = Column(String(50), nullable=True)   # project|license|contract|asset
    linked_resource_id   = Column(String(36), nullable=True)   # ID del recurso
    contract_id = Column(String(36), ForeignKey("contracts.id"), nullable=True)
    ci_id = Column(String(36), ForeignKey("sd_configuration_items.id"), nullable=True)
    service_item_id = Column(String(36), ForeignKey("sd_service_items.id"), nullable=True)

    problem_id = Column(String(36), ForeignKey("sd_problems.id"), nullable=True)
    parent_ticket_id = Column(String(36), ForeignKey("sd_tickets.id"), nullable=True)

    sla_policy_id = Column(String(36), ForeignKey("sd_sla_policies.id"), nullable=True)
    sla_response_due = Column(DateTime(timezone=True), nullable=True)
    sla_resolution_due = Column(DateTime(timezone=True), nullable=True)
    sla_response_status = Column(Enum(SLAStatus), default=SLAStatus.ok)
    sla_resolution_status = Column(Enum(SLAStatus), default=SLAStatus.ok)
    sla_paused_at = Column(DateTime(timezone=True), nullable=True)
    sla_pause_minutes = Column(Integer, default=0)

    resolution = Column(Text, nullable=True)
    resolution_code = Column(String(50), nullable=True)
    kb_article_id = Column(String(36), ForeignKey("sd_kb_articles.id"), nullable=True)

    csat_score = Column(Integer, nullable=True)
    csat_comment = Column(Text, nullable=True)
    csat_requested_at = Column(DateTime(timezone=True), nullable=True)

    time_spent_minutes = Column(Integer, default=0)

    first_response_at = Column(DateTime(timezone=True), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    first_response_minutes = Column(Integer, nullable=True)
    resolution_minutes = Column(Integer, nullable=True)
    sla_response_breached = Column(Boolean, default=False)
    sla_resolution_breached = Column(Boolean, default=False)
    # OLA de la cola: lo sella `ticket_events` al entrar en el grupo y lo
    # vigila `sla_monitor_service`. `ola_pause_base` son los minutos de pausa
    # que ya llevaba el ticket al entrar: solo cuenta la pausa en esta cola.
    group_assigned_at = Column(DateTime(timezone=True), nullable=True)
    ola_due = Column(DateTime(timezone=True), nullable=True)
    ola_pause_base = Column(Integer, nullable=True)
    ola_breached = Column(Boolean, default=False, nullable=False, server_default=sa_false())
    # UC: el contrato de soporte del proveedor mientras el ticket espera a un
    # tercero. El reloj lo sella `ticket_events` al entrar en `pending_third`
    # y lo vigila `sla_monitor_service`; el plazo es `resolution_hours` del
    # contrato (ALM).
    uc_contract_id = Column(String(36), ForeignKey("alm_contracts.id", ondelete="SET NULL"), nullable=True)
    uc_started_at = Column(DateTime(timezone=True), nullable=True)
    uc_due = Column(DateTime(timezone=True), nullable=True)
    uc_breached = Column(Boolean, default=False, nullable=False, server_default=sa_false())
    # Respuesta del proveedor: la anota el agente («El proveedor ha respondido»).
    uc_vendor_responded_at = Column(DateTime(timezone=True), nullable=True)
    uc_response_due = Column(DateTime(timezone=True), nullable=True)
    uc_response_breached = Column(Boolean, default=False, nullable=False, server_default=sa_false())

    # Phase 2 — Predictive Intelligence
    predicted_severity = Column(String(20), nullable=True)
    predicted_resolution_minutes = Column(Integer, nullable=True)
    escalation_risk_score = Column(Float, nullable=True)
    prediction_generated_at = Column(DateTime(timezone=True), nullable=True)

    # Phase 3 — AI Auto-Resolution
    auto_resolved = Column(Boolean, default=False, index=True)
    auto_resolved_at = Column(DateTime(timezone=True), nullable=True)
    auto_resolved_by = Column(String(100), nullable=True)  # "ai_auto_resolution" | user name
    auto_resolved_confidence = Column(Float, nullable=True)  # 0-1
    resolution_text = Column(Text, nullable=True)  # AI-suggested resolution
    root_cause = Column(String(255), nullable=True)  # AI-identified root cause
    resolution_kb_articles = Column(Text, nullable=True)  # JSON array of KB article numbers

    source = Column(String(20), default="portal")
    tags = Column(String(500), nullable=True)

    # Aprobacion del catalogo: NULL si el servicio no la pide; pending mientras
    # no se decide (no se puede trabajar), approved o rejected despues.
    approval_status = Column(String(20), nullable=True, index=True)

    # FIX: Use server_default so SQLite sets this correctly
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)

    requester_user = relationship("User", foreign_keys=[requester_user_id])
    requester_client = relationship("ClientUser", foreign_keys=[requester_client_id])
    assigned_to = relationship("User", foreign_keys=[assigned_to_user_id])
    uc_contract = relationship("ALMContract", foreign_keys=[uc_contract_id])
    client       = relationship("Client", foreign_keys=[client_id])
    created_by = relationship("User", foreign_keys=[created_by_user_id])
    assigned_group = relationship("AgentGroup")
    project = relationship("Project")
    ci = relationship("ConfigurationItem")
    # El otro extremo de `MajorIncident.tickets`. Ver la nota de
    # `major_incident_id` arriba para la decision de cardinalidad.
    major_incident = relationship(
        "MajorIncident", foreign_keys=[major_incident_id], back_populates="tickets")
    service_item = relationship("ServiceItem")
    sla_policy = relationship("SLAPolicy")
    kb_article = relationship("KBArticle", foreign_keys=[kb_article_id])
    comments = relationship("TicketComment", back_populates="ticket",
                            cascade="all, delete-orphan",
                            order_by="TicketComment.created_at")
    # FIX: TicketHistory uses 'changed_at', not 'created_at'
    history = relationship("TicketHistory", back_populates="ticket",
                           cascade="all, delete-orphan",
                           order_by="TicketHistory.changed_at")
    time_logs = relationship("TicketTimeLog", back_populates="ticket",
                             cascade="all, delete-orphan")
    child_tickets = relationship("Ticket", foreign_keys=[parent_ticket_id])
    known_error_links = relationship("KnownErrorTicket", back_populates="ticket", cascade="all, delete-orphan")

class TicketEvent(Base):
    """Lo que le ha pasado a un ticket, pendiente de avisar.

    Es una bandeja de salida: la fila se escribe en la MISMA transacción que el
    cambio (ver `ticket_events.py`), así que no hay aviso de un cambio que no se
    guardó ni cambio guardado que se quede sin aviso. Un trabajo de Celery la
    procesa después —avisos, correo, webhooks, flujos— y sella
    `processed_at`.
    """
    __tablename__ = "sd_ticket_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)
    ticket_id = Column(String(36), ForeignKey("sd_tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    # created | assigned | group_assigned | status_changed | priority_changed |
    # commented | sla_warning | sla_breached | escalated | approval_requested |
    # approval_decided
    kind = Column(String(40), nullable=False)
    data = Column(Text, nullable=True)  # JSON con el detalle de cada tipo
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    actor_client_id = Column(String(36), ForeignKey("client_users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    processed_at = Column(DateTime(timezone=True), nullable=True, index=True)
    attempts = Column(Integer, default=0, nullable=False)
    last_error = Column(String(500), nullable=True)

    ticket = relationship("Ticket")


class TicketApproval(Base):
    """La aprobacion que pide un servicio del catalogo antes de atenderse."""
    __tablename__ = "sd_ticket_approvals"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)
    ticket_id = Column(String(36), ForeignKey("sd_tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    approver_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    status = Column(String(20), default="pending", nullable=False, index=True)  # pending | approved | rejected
    comment = Column(Text, nullable=True)
    decided_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    ticket = relationship("Ticket")
    approver = relationship("User", foreign_keys=[approver_user_id])
    decided_by = relationship("User", foreign_keys=[decided_by_user_id])


class InboundMessage(Base):
    """Un correo (o mensaje de otro canal) ya procesado.

    El buzon se lee periodicamente y los webhooks se reintentan: sin esto, el
    mismo correo abriria dos tickets o dejaria dos comentarios.
    """
    __tablename__ = "sd_inbound_messages"
    __table_args__ = (UniqueConstraint("organization_id", "message_id", name="uq_sd_inbound_org_message"),)

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)
    message_id = Column(String(255), nullable=False)
    channel = Column(String(20), default="email", nullable=False)
    sender = Column(String(255), nullable=True)
    ticket_id = Column(String(36), ForeignKey("sd_tickets.id", ondelete="SET NULL"), nullable=True, index=True)
    outcome = Column(String(20), nullable=False)  # created | commented | ignored
    reason = Column(String(255), nullable=True)
    received_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class TicketComment(Base):
    __tablename__ = "sd_ticket_comments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    ticket_id = Column(String(36), ForeignKey("sd_tickets.id", ondelete="CASCADE"), nullable=False, index=True)

    body = Column(Text, nullable=False)
    is_public = Column(Boolean, default=True)
    is_solution = Column(Boolean, default=False)

    author_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    author_client_id = Column(String(36), ForeignKey("client_users.id"), nullable=True)
    author_name = Column(String(255), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    ticket = relationship("Ticket", back_populates="comments")
    author_user = relationship("User", foreign_keys=[author_user_id])
    author_client = relationship("ClientUser", foreign_keys=[author_client_id])

class TicketHistory(Base):
    """Immutable audit trail of all changes."""
    __tablename__ = "sd_ticket_history"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    ticket_id = Column(String(36), ForeignKey("sd_tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    field_name = Column(String(100), nullable=False)
    old_value = Column(String(500), nullable=True)
    new_value = Column(String(500), nullable=True)
    changed_by_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    # NOTE: This model uses 'changed_at', NOT 'created_at' — keep consistent
    changed_at = Column(DateTime(timezone=True), server_default=func.now())

    ticket = relationship("Ticket", back_populates="history")
    changed_by = relationship("User", foreign_keys=[changed_by_user_id])

class TicketTimeLog(Base):
    __tablename__ = "sd_ticket_time_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    ticket_id = Column(String(36), ForeignKey("sd_tickets.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    minutes = Column(Integer, nullable=False)
    description = Column(String(255), nullable=True)
    billable = Column(Boolean, default=False)
    logged_at = Column(DateTime(timezone=True), server_default=func.now())
    # La imputacion (parte de horas) que genero, si el ticket tiene proyecto:
    # es lo que lleva el tiempo del ticket a los partes y a la factura.
    imputation_id = Column(String(36), ForeignKey("imputations.id", ondelete="SET NULL"), nullable=True, index=True)

    ticket = relationship("Ticket", back_populates="time_logs")
    user = relationship("User", foreign_keys=[user_id])

class TicketLink(Base):
    __tablename__ = "sd_ticket_links"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    source_id    = Column(String(36), ForeignKey("sd_tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    target_id    = Column(String(36), ForeignKey("sd_tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    link_type    = Column(Enum(TicketLinkType), nullable=False)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
    created_by   = Column(String(36), ForeignKey("users.id"), nullable=True)

    source = relationship("Ticket", foreign_keys=[source_id])
    target = relationship("Ticket", foreign_keys=[target_id])

class TicketWatcher(Base):
    """Usuario que sigue un ticket para recibir notificaciones sin ser asignado."""
    __tablename__ = "sd_ticket_watchers"

    id         = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    ticket_id  = Column(String(36), ForeignKey("sd_tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id    = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    ticket = relationship("Ticket")
    user   = relationship("User", foreign_keys=[user_id])

class TicketMerge(Base):
    """Registro de cuando un ticket se fusiona con otro (duplicado detectado)."""
    __tablename__ = "sd_ticket_merges"

    id             = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    primary_id     = Column(String(36), ForeignKey("sd_tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    merged_id      = Column(String(36), ForeignKey("sd_tickets.id", ondelete="CASCADE"), nullable=False)
    reason         = Column(String(500), nullable=True)
    merged_by_user = Column(String(36), ForeignKey("users.id"), nullable=True)
    merged_at      = Column(DateTime(timezone=True), server_default=func.now())

    primary_ticket = relationship("Ticket", foreign_keys=[primary_id])
    merged_ticket  = relationship("Ticket", foreign_keys=[merged_id])
    merged_by      = relationship("User", foreign_keys=[merged_by_user])

class TicketTemplate(Base):
    __tablename__ = "sd_ticket_templates"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    name        = Column(String(255), nullable=False)
    ticket_type = Column(Enum(TicketType), nullable=False)
    category_id = Column(String(36), ForeignKey("sd_service_categories.id"), nullable=True)

    # JSON: [{field, label, type, required, options}]
    custom_fields = Column(Text, nullable=True)

    default_priority    = Column(Enum(TicketPriority), default=TicketPriority.p3_medium)
    default_group_id    = Column(String(36), ForeignKey("sd_agent_groups.id"), nullable=True)
    default_sla_id      = Column(String(36), ForeignKey("sd_sla_policies.id"), nullable=True)
    auto_assign_to_id   = Column(String(36), ForeignKey("users.id"), nullable=True)

    description_template = Column(Text, nullable=True)  # texto de ayuda para el solicitante
    is_active   = Column(Boolean, default=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())

class CannedResponse(Base):
    """Respuestas rápidas predefinidas para agentes de Service Desk."""
    __tablename__ = "sd_canned_responses"
    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    title       = Column(String(200), nullable=False)     # Nombre corto
    body        = Column(Text,        nullable=False)      # Texto de la respuesta
    category    = Column(String(100), nullable=True)       # Categoría para agrupar
    shortcut    = Column(String(50),  nullable=True)       # /shortcut para autocompletar
    is_active   = Column(Boolean,     default=True)
    created_by  = Column(String(36),  ForeignKey("users.id"), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())
    creator     = relationship("User", foreign_keys=[created_by])

class RoutingRule(Base):
    """Regla de routing automático: si condición → asignar a grupo/agente."""
    __tablename__ = "sd_routing_rules"

    id         = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    name       = Column(String(255), nullable=False)
    is_active  = Column(Boolean, default=True)
    priority   = Column(Integer, default=100)  # menor = mayor prioridad

    # Condiciones (JSON): {"ticket_type": "incident", "priority": ["p1_critical","p2_high"], "category_id": "..."}
    conditions = Column(Text, nullable=False, default="{}")
    # Acciones (JSON): {"assign_group": "id", "assign_user": "id", "set_priority": "p1_critical", "notify": ["email"]}
    actions    = Column(Text, nullable=False, default="{}")

    created_at = Column(DateTime(timezone=True), server_default=func.now())

class RoutingFeedback(Base):
    """Records routing outcomes per ticket for ML model learning.

    Written when a ticket is assigned (routed_at + context) and updated
    when it closes (resolution_minutes, csat_score, reopened).
    """
    __tablename__ = "sd_routing_feedback"

    id                  = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    ticket_id           = Column(String(36), ForeignKey("sd_tickets.id", ondelete="SET NULL"), nullable=True, index=True)
    assigned_agent_id   = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    ticket_type         = Column(String(30), nullable=True, index=True)
    category_id         = Column(String(36), ForeignKey("sd_service_categories.id", ondelete="SET NULL"), nullable=True, index=True)
    priority            = Column(String(20), nullable=True)
    support_level       = Column(String(10), nullable=True)
    resolution_minutes  = Column(Integer, nullable=True)     # filled on close
    csat_score          = Column(Integer, nullable=True)     # 1-5, filled on CSAT submit
    reopened            = Column(Boolean, default=False, nullable=False)
    routed_at           = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    outcome_recorded_at = Column(DateTime(timezone=True), nullable=True)
