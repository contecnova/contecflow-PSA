from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
import uuid

from app.db.base import Base


class PortalConversationStatus(str, enum.Enum):
    draft = "draft"
    active = "active"
    pending_approval = "pending_approval"
    restricted = "restricted"
    closed = "closed"
    archived = "archived"


class PortalConversationAssignmentMode(str, enum.Enum):
    manual = "manual"
    round_robin = "round_robin"
    role_pool = "role_pool"
    owner_based = "owner_based"


class PortalConversationParticipantType(str, enum.Enum):
    internal_user = "internal_user"
    client_user = "client_user"
    internal_role = "internal_role"
    client_org = "client_org"


class PortalConversationRole(str, enum.Enum):
    owner = "owner"
    agent = "agent"
    watcher = "watcher"
    approver = "approver"
    requester = "requester"


class PortalConversationMessageType(str, enum.Enum):
    text = "text"
    system = "system"
    approval_request = "approval_request"
    approval_decision = "approval_decision"
    attachment = "attachment"
    ai_summary = "ai_summary"


class PortalConversationClassification(str, enum.Enum):
    public_client = "public_client"
    internal_restricted = "internal_restricted"
    confidential = "confidential"


class PortalConversationGRCStatus(str, enum.Enum):
    allowed = "allowed"
    blocked = "blocked"
    redacted = "redacted"
    pending_review = "pending_review"


class PortalConversationSource(str, enum.Enum):
    native = "native"
    legacy_client_message = "legacy_client_message"


class PortalConversationPolicy(Base):
    __tablename__ = "portal_conversation_policies"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    topic_type = Column(String(50), nullable=False, index=True)
    is_active = Column(Boolean, nullable=False, default=True)
    requires_client_message_approval = Column(Boolean, nullable=False, default=False)
    requires_team_message_approval = Column(Boolean, nullable=False, default=False)
    redact_sensitive_content = Column(Boolean, nullable=False, default=True)
    allow_legacy_federation = Column(Boolean, nullable=False, default=True)
    assignment_mode = Column(Enum(PortalConversationAssignmentMode), nullable=False, default=PortalConversationAssignmentMode.manual)
    default_group_id = Column(String(36), ForeignKey("sd_agent_groups.id", ondelete="SET NULL"), nullable=True, index=True)
    default_role_key = Column(String(50), nullable=True)
    first_response_hours = Column(Integer, nullable=False, default=8)
    escalation_hours = Column(Integer, nullable=False, default=24)
    approval_role_key = Column(String(50), nullable=True)
    approval_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    sensitive_keywords = Column(Text, nullable=True, default='["iban","password","secret","dni","token","api_key"]')
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    organization = relationship("Organization")
    default_group = relationship("AgentGroup", foreign_keys=[default_group_id])
    approval_user = relationship("User", foreign_keys=[approval_user_id])


class PortalConversation(Base):
    __tablename__ = "portal_conversations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    is_active = Column(Boolean, default=True, nullable=False, server_default="1", index=True)  # audit #36 soft-delete
    client_org_id = Column(String(36), ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    topic_type = Column(String(50), nullable=False, default="general")
    source = Column(Enum(PortalConversationSource), nullable=False, default=PortalConversationSource.native, index=True)
    legacy_thread_id = Column(String(36), nullable=True, index=True)
    source_resource_type = Column(String(50), nullable=True)
    source_resource_id = Column(String(36), nullable=True, index=True)
    title = Column(String(255), nullable=False)
    status = Column(Enum(PortalConversationStatus), nullable=False, default=PortalConversationStatus.active, index=True)
    assignment_mode = Column(Enum(PortalConversationAssignmentMode), nullable=False, default=PortalConversationAssignmentMode.manual)
    visibility_policy_key = Column(String(100), nullable=True)
    sla_policy_id = Column(String(36), ForeignKey("sd_sla_policies.id", ondelete="SET NULL"), nullable=True, index=True)
    policy_id = Column(String(36), ForeignKey("portal_conversation_policies.id", ondelete="SET NULL"), nullable=True, index=True)
    assigned_group_id = Column(String(36), ForeignKey("sd_agent_groups.id", ondelete="SET NULL"), nullable=True, index=True)
    assigned_role_key = Column(String(50), nullable=True)
    first_response_due_at = Column(DateTime(timezone=True), nullable=True, index=True)
    first_response_at = Column(DateTime(timezone=True), nullable=True)
    escalated_at = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_by_client_id = Column(String(36), ForeignKey("client_users.id", ondelete="SET NULL"), nullable=True, index=True)
    last_message_at = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    organization = relationship("Organization")
    client_org = relationship("Client", foreign_keys=[client_org_id])
    project = relationship("Project", foreign_keys=[project_id])
    policy = relationship("PortalConversationPolicy", foreign_keys=[policy_id])
    assigned_group = relationship("AgentGroup", foreign_keys=[assigned_group_id])
    created_by_user = relationship("User", foreign_keys=[created_by_user_id])
    created_by_client = relationship("ClientUser", foreign_keys=[created_by_client_id])
    participants = relationship("PortalConversationParticipant", back_populates="conversation", cascade="all, delete-orphan")
    messages = relationship("PortalConversationMessage", back_populates="conversation", cascade="all, delete-orphan", order_by="PortalConversationMessage.created_at")
    audits = relationship("PortalConversationAudit", back_populates="conversation", cascade="all, delete-orphan", order_by="PortalConversationAudit.created_at")


class PortalConversationParticipant(Base):
    __tablename__ = "portal_conversation_participants"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)  # audit #7
    conversation_id = Column(String(36), ForeignKey("portal_conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    participant_type = Column(Enum(PortalConversationParticipantType), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    client_user_id = Column(String(36), ForeignKey("client_users.id", ondelete="SET NULL"), nullable=True, index=True)
    client_org_id = Column(String(36), ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True)
    role_key = Column(String(50), nullable=True)
    role_in_conversation = Column(Enum(PortalConversationRole), nullable=False, default=PortalConversationRole.agent)
    can_read = Column(Boolean, nullable=False, default=True)
    can_write = Column(Boolean, nullable=False, default=True)
    can_invite = Column(Boolean, nullable=False, default=False)
    can_close = Column(Boolean, nullable=False, default=False)
    joined_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    removed_at = Column(DateTime(timezone=True), nullable=True)
    added_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    conversation = relationship("PortalConversation", back_populates="participants")
    user = relationship("User", foreign_keys=[user_id])
    client_user = relationship("ClientUser", foreign_keys=[client_user_id])
    client_org = relationship("Client", foreign_keys=[client_org_id])
    added_by_user = relationship("User", foreign_keys=[added_by_user_id])


class PortalConversationMessage(Base):
    __tablename__ = "portal_conversation_messages"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(String(36), ForeignKey("portal_conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    parent_message_id = Column(String(36), ForeignKey("portal_conversation_messages.id", ondelete="SET NULL"), nullable=True, index=True)
    sender_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    sender_client_id = Column(String(36), ForeignKey("client_users.id", ondelete="SET NULL"), nullable=True, index=True)
    legacy_message_id = Column(String(36), ForeignKey("client_messages.id", ondelete="SET NULL"), nullable=True, index=True)
    approval_request_id = Column(String(36), ForeignKey("approval_requests.id", ondelete="SET NULL"), nullable=True, index=True)
    message_type = Column(Enum(PortalConversationMessageType), nullable=False, default=PortalConversationMessageType.text)
    body = Column(Text, nullable=False)
    raw_body = Column(Text, nullable=True)
    moderation_notes = Column(Text, nullable=True)
    is_internal_note = Column(Boolean, nullable=False, default=False)
    is_redacted = Column(Boolean, nullable=False, default=False)
    classification = Column(Enum(PortalConversationClassification), nullable=False, default=PortalConversationClassification.public_client)
    grc_status = Column(Enum(PortalConversationGRCStatus), nullable=False, default=PortalConversationGRCStatus.allowed, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    read_at = Column(DateTime(timezone=True), nullable=True)
    # Migracion 209 (chat del portal completo, docs/portal/CHAT_DEL_PORTAL.md):
    # edicion y borrado del propio mensaje con rastro (versiones + auditoria).
    edited_at = Column(DateTime(timezone=True), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)
    deleted_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    deleted_by_client_id = Column(String(36), ForeignKey("client_users.id", ondelete="SET NULL"), nullable=True, index=True)

    conversation = relationship("PortalConversation", back_populates="messages")
    organization = relationship("Organization")
    project = relationship("Project", foreign_keys=[project_id])
    parent_message = relationship("PortalConversationMessage", remote_side=[id])
    sender_user = relationship("User", foreign_keys=[sender_user_id])
    sender_client = relationship("ClientUser", foreign_keys=[sender_client_id])
    legacy_message = relationship("ClientMessage", foreign_keys=[legacy_message_id])
    approval_request = relationship("ApprovalRequest", foreign_keys=[approval_request_id])
    attachments = relationship("PortalConversationAttachment", back_populates="message",
                               order_by="PortalConversationAttachment.created_at")
    reactions = relationship("PortalConversationReaction", back_populates="message",
                             cascade="all, delete-orphan", order_by="PortalConversationReaction.created_at")


class PortalConversationAudit(Base):
    __tablename__ = "portal_conversation_audits"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(String(36), ForeignKey("portal_conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    actor_client_id = Column(String(36), ForeignKey("client_users.id", ondelete="SET NULL"), nullable=True, index=True)
    action_type = Column(String(100), nullable=False, index=True)
    target_type = Column(String(50), nullable=True)
    target_id = Column(String(36), nullable=True)
    status = Column(String(20), nullable=False, default="success")
    details = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    conversation = relationship("PortalConversation", back_populates="audits")
    organization = relationship("Organization")
    actor_user = relationship("User", foreign_keys=[actor_user_id])
    actor_client = relationship("ClientUser", foreign_keys=[actor_client_id])


# ── Migracion 209: chat del portal completo (docs/portal/CHAT_DEL_PORTAL.md) ──

class PortalConversationMessageVersion(Base):
    """Rastro de ediciones y borrados: el texto ANTERIOR de cada cambio.

    Lo ve el equipo (no el cliente). Entra en la retencion
    (`portal_conversation_message_versions`) y en la supresion RGPD.
    """
    __tablename__ = "portal_conversation_message_versions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    message_id = Column(String(36), ForeignKey("portal_conversation_messages.id", ondelete="CASCADE"), nullable=False, index=True)
    body = Column(Text, nullable=True)
    raw_body = Column(Text, nullable=True)
    change_type = Column(String(10), nullable=False, default="edit")  # edit | delete
    edited_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    edited_by_client_id = Column(String(36), ForeignKey("client_users.id", ondelete="SET NULL"), nullable=True, index=True)
    edited_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class PortalConversationAttachment(Base):
    """Imagen o fichero de un mensaje del chat del portal.

    El fichero vive en el almacen de objetos (`collaboration._storage`), con la
    clave segmentada por empresa y conversacion. Solo lo descargan los
    participantes de la conversacion de la misma empresa, por la API (nunca por
    enlace firmado al portador). Borrar la fila (retencion, cascada) borra el
    fichero al confirmar; el bloqueo legal impide ambas cosas.
    """
    __tablename__ = "portal_conversation_attachments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = Column(String(36), ForeignKey("portal_conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    message_id = Column(String(36), ForeignKey("portal_conversation_messages.id", ondelete="CASCADE"), nullable=True, index=True)
    uploaded_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    uploaded_by_client_id = Column(String(36), ForeignKey("client_users.id", ondelete="SET NULL"), nullable=True, index=True)
    name = Column(String(255), nullable=False)
    mime_type = Column(String(160), nullable=True)
    size_bytes = Column(Integer, nullable=False, default=0)
    storage_provider = Column(String(40), nullable=False, default="local")
    storage_key = Column(String(800), nullable=False)
    sha256 = Column(String(64), nullable=True)
    av_status = Column(String(40), nullable=False, default="pending")
    dlp_status = Column(String(40), nullable=False, default="pending")
    is_quarantined = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    message = relationship("PortalConversationMessage", back_populates="attachments")


class PortalConversationReaction(Base):
    __tablename__ = "portal_conversation_reactions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    message_id = Column(String(36), ForeignKey("portal_conversation_messages.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    client_user_id = Column(String(36), ForeignKey("client_users.id", ondelete="CASCADE"), nullable=True, index=True)
    emoji = Column(String(32), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    message = relationship("PortalConversationMessage", back_populates="reactions")

    # 24-11-2026: únicos por empresa (organization_id delante), como el resto de tablas con
    # empresa (tests/test_unicos_por_organizacion.py); el mensaje ya es de una sola empresa.
    __table_args__ = (
        UniqueConstraint("organization_id", "message_id", "user_id", "emoji", name="uq_portal_conv_reaction_user"),
        UniqueConstraint("organization_id", "message_id", "client_user_id", "emoji", name="uq_portal_conv_reaction_client"),
    )


class PortalConversationCall(Base):
    """Llamada o videollamada del chat del portal.

    SOLO la inicia el equipo: el cliente acepta, rechaza o cuelga, nunca inicia
    (se impone en el servidor con 403 `portal_llamada_solo_operador`). Estados:
    ringing, active, declined, missed, ended. No se graban ni se transcriben.
    """
    __tablename__ = "portal_conversation_calls"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = Column(String(36), ForeignKey("portal_conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    initiated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    kind = Column(String(10), nullable=False, default="audio")  # audio | video
    status = Column(String(20), nullable=False, default="ringing", index=True)
    livekit_room = Column(String(160), nullable=False)
    answered_by_client_id = Column(String(36), ForeignKey("client_users.id", ondelete="SET NULL"), nullable=True, index=True)
    declined_by_client_id = Column(String(36), ForeignKey("client_users.id", ondelete="SET NULL"), nullable=True, index=True)
    ended_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    ended_by_client_id = Column(String(36), ForeignKey("client_users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    answered_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Integer, nullable=False, default=0)


# Ficheros de adjuntos borrados por fila (retención, cascada, supresión): se quitan del
# almacén DESPUÉS de confirmar. 24-11-2026: los oyentes viven en app/db/portal_chat_borrado.py
# (un modelo no importa servicios); los registra app/models/__init__.py.
