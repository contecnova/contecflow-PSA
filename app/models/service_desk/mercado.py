"""Service desk — mejoras de mercado (16-11-2026, migracion 174).

Tablas nuevas:

* `sd_service_item_tasks`: tareas de ejecucion estructuradas de un servicio del
  catalogo (cola, persona, SLA propio y etapa). Sustituyen al JSON
  `sd_service_items.fulfillment_tasks`, que la migracion vuelca aqui.
* `sd_sla_rules`: SLA condicionales. La primera regla activa que encaja
  (servicio, tipo de ticket, cliente, contrato, prioridad; vacio = cualquiera)
  fija las horas de respuesta y resolucion; sin regla, la politica de siempre.
* `sd_ola_targets`: objetivo del OLA de una cola por prioridad; sin fila, el
  `ola_hours` de la cola.
* `sd_ticket_lifecycles`, `sd_ticket_lifecycle_states` y
  `sd_ticket_lifecycle_transitions`: estados y ciclos de vida por tipo de
  ticket. Cada estado propio cae en un estado base (`TicketStatus`), que es lo
  que leen el SLA, las pausas, los avisos y los informes.
* `sd_channel_conversations` y `sd_channel_messages`: conversaciones de los
  canales (WhatsApp, chat en vivo del portal, Slack) con su ticket y el
  traspaso a un agente.
* `sd_ci_classes`: clases de CI de la empresa. Cada una se apoya en una clase
  base (`CIType`), que es la que entienden el descubrimiento y el impacto.
* `sd_portal_assistant_actions`: lo que el asistente del portal propone hacer
  y el cliente confirma (o no).
"""
import uuid

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.db.base import Base


def _id():
    return str(uuid.uuid4())


class ServiceItemTask(Base):
    __tablename__ = "sd_service_item_tasks"

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)
    service_item_id = Column(String(36), ForeignKey("sd_service_items.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    group_id = Column(String(36), ForeignKey("sd_agent_groups.id", ondelete="SET NULL"), nullable=True, index=True)
    assignee_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    # Horas para resolverla (en el calendario del SLA de la peticion); vacio: las del servicio.
    sla_hours = Column(Float, nullable=True)
    # Etapa: las de la misma etapa van a la vez; la siguiente empieza al acabar todas.
    stage = Column(Integer, nullable=False, default=1, server_default="1")
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SLARule(Base):
    __tablename__ = "sd_sla_rules"

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)
    name = Column(String(150), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    # Condiciones (vacio = cualquiera)
    service_item_id = Column(String(36), ForeignKey("sd_service_items.id", ondelete="CASCADE"), nullable=True, index=True)
    ticket_type = Column(String(30), nullable=True)
    client_id = Column(String(36), ForeignKey("clients.id", ondelete="CASCADE"), nullable=True, index=True)
    contract_id = Column(String(36), ForeignKey("contracts.id", ondelete="CASCADE"), nullable=True, index=True)
    priority = Column(String(20), nullable=True)
    # Objetivos
    response_hours = Column(Float, nullable=True)
    resolution_hours = Column(Float, nullable=True)
    # Calendario: el de esta politica (vacio: el de la politica que ya tenga el ticket)
    sla_policy_id = Column(String(36), ForeignKey("sd_sla_policies.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class OLATarget(Base):
    __tablename__ = "sd_ola_targets"
    __table_args__ = (UniqueConstraint("group_id", "priority", name="uq_sd_ola_targets_group_priority"),)

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)
    group_id = Column(String(36), ForeignKey("sd_agent_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    priority = Column(String(20), nullable=False)
    hours = Column(Float, nullable=False)


class TicketLifecycle(Base):
    __tablename__ = "sd_ticket_lifecycles"
    __table_args__ = (UniqueConstraint("organization_id", "ticket_type", name="uq_sd_lifecycle_org_type"),)

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)
    ticket_type = Column(String(30), nullable=False)
    name = Column(String(150), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")
    # Sin transiciones declaradas, cualquier estado lleva a cualquier otro.
    restrict_transitions = Column(Boolean, nullable=False, default=False, server_default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class TicketLifecycleState(Base):
    __tablename__ = "sd_ticket_lifecycle_states"
    __table_args__ = (UniqueConstraint("lifecycle_id", "key", name="uq_sd_lifecycle_state_key"),)

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)
    lifecycle_id = Column(String(36), ForeignKey("sd_ticket_lifecycles.id", ondelete="CASCADE"), nullable=False, index=True)
    key = Column(String(50), nullable=False)
    label = Column(String(100), nullable=False)
    # Estado base de `TicketStatus`: SLA, pausas, avisos e informes lo leen a el.
    base_status = Column(String(20), nullable=False)
    is_initial = Column(Boolean, nullable=False, default=False, server_default="0")
    color = Column(String(30), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")


class TicketLifecycleTransition(Base):
    __tablename__ = "sd_ticket_lifecycle_transitions"
    __table_args__ = (UniqueConstraint("lifecycle_id", "from_key", "to_key", name="uq_sd_lifecycle_transition"),)

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)
    lifecycle_id = Column(String(36), ForeignKey("sd_ticket_lifecycles.id", ondelete="CASCADE"), nullable=False, index=True)
    from_key = Column(String(50), nullable=False)
    to_key = Column(String(50), nullable=False)


class ChannelConversation(Base):
    __tablename__ = "sd_channel_conversations"

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)
    channel = Column(String(20), nullable=False, index=True)          # whatsapp | livechat | slack | teams
    external_id = Column(String(255), nullable=True, index=True)      # telefono, sesion, canal+hilo
    ticket_id = Column(String(36), ForeignKey("sd_tickets.id", ondelete="SET NULL"), nullable=True, index=True)
    client_user_id = Column(String(36), ForeignKey("client_users.id", ondelete="SET NULL"), nullable=True, index=True)
    visitor_name = Column(String(255), nullable=True)
    language = Column(String(8), nullable=True)
    # bot: atiende el asistente; waiting_agent: pidio una persona; agent: la tiene un agente; closed
    status = Column(String(20), nullable=False, default="bot", server_default="bot", index=True)
    assigned_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    last_message_at = Column(DateTime(timezone=True), nullable=True)
    # Migracion 179 (canales en tiempo real): «leido» de cada lado y ultimo
    # mensaje del cliente (ventana de 24 h de WhatsApp).
    client_read_at = Column(DateTime(timezone=True), nullable=True)
    agent_read_at = Column(DateTime(timezone=True), nullable=True)
    last_inbound_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ChannelMessage(Base):
    __tablename__ = "sd_channel_messages"
    __table_args__ = (UniqueConstraint("conversation_id", "external_message_id", name="uq_sd_channel_message_ext"),)

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)
    conversation_id = Column(String(36), ForeignKey("sd_channel_conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    direction = Column(String(3), nullable=False)          # in | out
    author_type = Column(String(10), nullable=False)       # customer | agent | bot | system
    author_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    body = Column(Text, nullable=False)
    external_message_id = Column(String(255), nullable=True)
    # Traduccion en tiempo real (migracion 175): idioma de `body` (lo que vio el cliente).
    language = Column(String(16), nullable=True)
    # Migracion 179: el comentario del ticket que es o que lo origino (sin
    # bucles ni duplicados entre canal y ticket), el adjunto que lleva y como
    # se entrego (sent | template | failed | outside_window).
    ticket_comment_id = Column(String(36), ForeignKey("sd_ticket_comments.id", ondelete="SET NULL"),
                               nullable=True, index=True)
    attachment_document_id = Column(String(36), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    delivery_status = Column(String(20), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class CIClass(Base):
    __tablename__ = "sd_ci_classes"
    __table_args__ = (UniqueConstraint("organization_id", "key", name="uq_sd_ci_class_org_key"),)

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)
    key = Column(String(50), nullable=False)
    label = Column(String(100), nullable=False)
    # Clase base (`CIType`) que entienden el descubrimiento, el impacto y la topologia.
    base_type = Column(String(30), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PortalAssistantAction(Base):
    __tablename__ = "sd_portal_assistant_actions"

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)
    client_user_id = Column(String(36), ForeignKey("client_users.id", ondelete="CASCADE"), nullable=False, index=True)
    action = Column(String(40), nullable=False)            # ticket_status | catalog_request | password_reset
    params_json = Column(Text, nullable=True)
    # proposed -> executed | cancelled | failed | expired
    status = Column(String(12), nullable=False, default="proposed", server_default="proposed")
    result_json = Column(Text, nullable=True)
    # Migracion 179: quien entendio la peticion (ai | rules).
    engine = Column(String(10), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    decided_at = Column(DateTime(timezone=True), nullable=True)
