from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, String, Text
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
    default_group_id = Column(String(36), ForeignKey("sd_agent_groups.id"), nullable=True)
    default_role_key = Column(String(50), nullable=True)
    first_response_hours = Column(Integer, nullable=False, default=8)
    escalation_hours = Column(Integer, nullable=False, default=24)
    approval_role_key = Column(String(50), nullable=True)
    approval_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
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
    sla_policy_id = Column(String(36), ForeignKey("sd_sla_policies.id"), nullable=True)
    policy_id = Column(String(36), ForeignKey("portal_conversation_policies.id", ondelete="SET NULL"), nullable=True, index=True)
    assigned_group_id = Column(String(36), ForeignKey("sd_agent_groups.id"), nullable=True)
    assigned_role_key = Column(String(50), nullable=True)
    first_response_due_at = Column(DateTime(timezone=True), nullable=True, index=True)
    first_response_at = Column(DateTime(timezone=True), nullable=True)
    escalated_at = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_by_client_id = Column(String(36), ForeignKey("client_users.id"), nullable=True)
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
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    conversation_id = Column(String(36), ForeignKey("portal_conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    participant_type = Column(Enum(PortalConversationParticipantType), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    client_user_id = Column(String(36), ForeignKey("client_users.id"), nullable=True, index=True)
    client_org_id = Column(String(36), ForeignKey("clients.id"), nullable=True, index=True)
    role_key = Column(String(50), nullable=True)
    role_in_conversation = Column(Enum(PortalConversationRole), nullable=False, default=PortalConversationRole.agent)
    can_read = Column(Boolean, nullable=False, default=True)
    can_write = Column(Boolean, nullable=False, default=True)
    can_invite = Column(Boolean, nullable=False, default=False)
    can_close = Column(Boolean, nullable=False, default=False)
    joined_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    removed_at = Column(DateTime(timezone=True), nullable=True)
    added_by_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)

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
    sender_user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    sender_client_id = Column(String(36), ForeignKey("client_users.id"), nullable=True, index=True)
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

    conversation = relationship("PortalConversation", back_populates="messages")
    organization = relationship("Organization")
    project = relationship("Project", foreign_keys=[project_id])
    parent_message = relationship("PortalConversationMessage", remote_side=[id])
    sender_user = relationship("User", foreign_keys=[sender_user_id])
    sender_client = relationship("ClientUser", foreign_keys=[sender_client_id])
    legacy_message = relationship("ClientMessage", foreign_keys=[legacy_message_id])
    approval_request = relationship("ApprovalRequest", foreign_keys=[approval_request_id])


class PortalConversationAudit(Base):
    __tablename__ = "portal_conversation_audits"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(String(36), ForeignKey("portal_conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    actor_client_id = Column(String(36), ForeignKey("client_users.id"), nullable=True, index=True)
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