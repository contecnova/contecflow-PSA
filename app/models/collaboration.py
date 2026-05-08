"""
Collaboration domain models — Teams-like internal chat.

Tables (per `chat_interno_teams_solucion_final.txt`):
  - collaboration_workspaces
  - collaboration_teams
  - collaboration_team_members
  - collaboration_channels
  - collaboration_channel_members
  - collaboration_direct_conversations
  - collaboration_group_conversations
  - collaboration_conversation_members
  - collaboration_messages
  - collaboration_message_versions
  - collaboration_threads
  - collaboration_reactions
  - collaboration_mentions
  - collaboration_reads
  - collaboration_attachments
  - collaboration_attachment_versions
  - collaboration_calls
  - collaboration_call_participants
  - collaboration_recordings
  - collaboration_transcripts
  - collaboration_notifications
  - collaboration_presence_states
  - collaboration_integrations
  - collaboration_webhooks
  - collaboration_bot_apps
  - collaboration_moderation_cases
  - collaboration_retention_policies
  - collaboration_legal_holds
  - collaboration_audit_events

Plus internal helper table for FK consistency:
  - collaboration_conversations  (parent: kind = channel | direct | group)
  - collaboration_pinned_messages, collaboration_saved_messages,
    collaboration_scheduled_messages, collaboration_drafts,
    collaboration_notification_rules, collaboration_bot_executions,
    collaboration_slash_command_logs

Multi-tenant: every table carries `organization_id` (FK to organizations.id).
"""
from __future__ import annotations

import enum
import uuid
from sqlalchemy import (
    Boolean, Column, DateTime, Enum, ForeignKey, Index,
    Integer, JSON, LargeBinary, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


def _uid() -> str:
    return str(uuid.uuid4())


# ── Enums ────────────────────────────────────────────────────────────────────
class ConversationKind(str, enum.Enum):
    channel = "channel"
    direct = "direct"
    group = "group"


class ChannelType(str, enum.Enum):
    public = "public"
    private = "private"
    announcement = "announcement"
    project = "project"  # auto-synced from PSA project


class TeamRole(str, enum.Enum):
    owner = "owner"
    admin = "admin"
    member = "member"
    guest = "guest"


class ChannelRole(str, enum.Enum):
    owner = "owner"
    moderator = "moderator"
    member = "member"


class MessageType(str, enum.Enum):
    text = "text"
    system = "system"
    file = "file"
    call = "call"
    bot = "bot"
    poll = "poll"
    decision = "decision"
    summary = "summary"


class MessageStatus(str, enum.Enum):
    visible = "visible"
    edited = "edited"
    deleted = "deleted"


class ReactionEmoji(str, enum.Enum):
    thumbs_up = "thumbs_up"
    thumbs_down = "thumbs_down"
    heart = "heart"
    eyes = "eyes"
    fire = "fire"
    rocket = "rocket"
    check = "check"
    x = "x"
    party = "party"
    raised_hands = "raised_hands"


class CallKind(str, enum.Enum):
    audio = "audio"
    video = "video"


class CallStatus(str, enum.Enum):
    ringing = "ringing"
    active = "active"
    ended = "ended"
    missed = "missed"
    cancelled = "cancelled"


class PresenceStatus(str, enum.Enum):
    online = "online"
    away = "away"
    busy = "busy"
    do_not_disturb = "do_not_disturb"
    offline = "offline"


class NotificationKind(str, enum.Enum):
    message = "message"
    mention = "mention"
    reply = "reply"
    reaction = "reaction"
    call = "call"
    join = "join"
    leave = "leave"
    bot = "bot"
    moderation = "moderation"
    system = "system"


class ModerationVerdict(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    redacted = "redacted"
    quarantined = "quarantined"
    blocked = "blocked"


class IntegrationKind(str, enum.Enum):
    jira = "jira"
    github = "github"
    gitlab = "gitlab"
    google_calendar = "google_calendar"
    microsoft_365 = "microsoft_365"
    service_desk = "service_desk"
    nexus_ai = "nexus_ai"
    custom_webhook = "custom_webhook"


class BotKind(str, enum.Enum):
    nexus = "nexus"
    oracle = "oracle"
    pulse = "pulse"
    watcher = "watcher"
    bridge = "bridge"
    compliance = "compliance"
    custom = "custom"


# ── 1. Workspaces ────────────────────────────────────────────────────────────
class CollaborationWorkspace(Base):
    """Top-level workspace per organization. One per org, created on first use."""
    __tablename__ = "collaboration_workspaces"

    id = Column(String(36), primary_key=True, default=_uid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    name = Column(String(120), nullable=False)
    icon_url = Column(String(500), nullable=True)
    primary_color = Column(String(20), nullable=True)
    settings = Column(JSON, nullable=False, default=dict)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    organization = relationship("Organization")


# ── 2. Teams + 3. Members ─────────────────────────────────────────────────────
class CollaborationTeam(Base):
    __tablename__ = "collaboration_teams"

    id = Column(String(36), primary_key=True, default=_uid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id = Column(String(36), ForeignKey("collaboration_workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    slug = Column(String(140), nullable=False)
    description = Column(Text, nullable=True)
    is_private = Column(Boolean, nullable=False, default=False)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)  # auto-sync
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    is_archived = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    workspace = relationship("CollaborationWorkspace")
    project = relationship("Project")
    members = relationship("CollaborationTeamMember", back_populates="team", cascade="all, delete-orphan")
    channels = relationship("CollaborationChannel", back_populates="team", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("workspace_id", "slug", name="uq_team_slug_workspace"),)


class CollaborationTeamMember(Base):
    __tablename__ = "collaboration_team_members"

    id = Column(String(36), primary_key=True, default=_uid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    team_id = Column(String(36), ForeignKey("collaboration_teams.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(Enum(TeamRole), nullable=False, default=TeamRole.member)
    joined_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    team = relationship("CollaborationTeam", back_populates="members")
    user = relationship("User")

    __table_args__ = (UniqueConstraint("team_id", "user_id", name="uq_team_member"),)


# ── Internal: parent conversation ────────────────────────────────────────────
class CollaborationConversation(Base):
    """Unifies channel/direct/group for FK-target consistency."""
    __tablename__ = "collaboration_conversations"

    id = Column(String(36), primary_key=True, default=_uid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = Column(Enum(ConversationKind), nullable=False, index=True)
    workspace_id = Column(String(36), ForeignKey("collaboration_workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    last_activity_at = Column(DateTime(timezone=True), nullable=True, index=True)
    last_message_id = Column(String(36), nullable=True)
    is_archived = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ── 4. Channels + 5. Channel members ─────────────────────────────────────────
class CollaborationChannel(Base):
    __tablename__ = "collaboration_channels"

    id = Column(String(36), primary_key=True, default=_uid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id = Column(String(36), ForeignKey("collaboration_workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    team_id = Column(String(36), ForeignKey("collaboration_teams.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = Column(String(36), ForeignKey("collaboration_conversations.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    name = Column(String(120), nullable=False)
    slug = Column(String(140), nullable=False)
    topic = Column(String(500), nullable=True)
    description = Column(Text, nullable=True)
    channel_type = Column(Enum(ChannelType), nullable=False, default=ChannelType.public)
    is_default = Column(Boolean, nullable=False, default=False)
    is_archived = Column(Boolean, nullable=False, default=False)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    team = relationship("CollaborationTeam", back_populates="channels")
    conversation = relationship("CollaborationConversation", foreign_keys=[conversation_id])
    members = relationship("CollaborationChannelMember", back_populates="channel", cascade="all, delete-orphan")
    project = relationship("Project")

    __table_args__ = (UniqueConstraint("team_id", "slug", name="uq_channel_slug_team"),)


class CollaborationChannelMember(Base):
    __tablename__ = "collaboration_channel_members"

    id = Column(String(36), primary_key=True, default=_uid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    channel_id = Column(String(36), ForeignKey("collaboration_channels.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(Enum(ChannelRole), nullable=False, default=ChannelRole.member)
    last_read_message_id = Column(String(36), nullable=True)
    last_read_at = Column(DateTime(timezone=True), nullable=True)
    notify_level = Column(String(20), nullable=False, default="all")  # all | mentions | none
    is_starred = Column(Boolean, nullable=False, default=False)
    is_muted = Column(Boolean, nullable=False, default=False)
    joined_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    channel = relationship("CollaborationChannel", back_populates="members")
    user = relationship("User")

    __table_args__ = (UniqueConstraint("channel_id", "user_id", name="uq_channel_member"),)


# ── 6/7. Direct + Group conversations ────────────────────────────────────────
class CollaborationDirectConversation(Base):
    __tablename__ = "collaboration_direct_conversations"

    id = Column(String(36), primary_key=True, default=_uid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id = Column(String(36), ForeignKey("collaboration_workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = Column(String(36), ForeignKey("collaboration_conversations.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    user_a_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    user_b_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # External participant: client portal user (for cross-org channels)
    client_user_a_id = Column(String(36), ForeignKey("client_users.id", ondelete="SET NULL"), nullable=True, index=True)
    client_user_b_id = Column(String(36), ForeignKey("client_users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    conversation = relationship("CollaborationConversation", foreign_keys=[conversation_id])

    __table_args__ = (
        Index("ix_direct_conv_pair", "user_a_id", "user_b_id"),
    )


class CollaborationGroupConversation(Base):
    __tablename__ = "collaboration_group_conversations"

    id = Column(String(36), primary_key=True, default=_uid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id = Column(String(36), ForeignKey("collaboration_workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = Column(String(36), ForeignKey("collaboration_conversations.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    title = Column(String(160), nullable=True)
    icon_url = Column(String(500), nullable=True)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    conversation = relationship("CollaborationConversation", foreign_keys=[conversation_id])
    members = relationship("CollaborationConversationMember", back_populates="group", cascade="all, delete-orphan")


# ── 8. Conversation members (for direct + group) ─────────────────────────────
class CollaborationConversationMember(Base):
    __tablename__ = "collaboration_conversation_members"

    id = Column(String(36), primary_key=True, default=_uid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = Column(String(36), ForeignKey("collaboration_conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    group_id = Column(String(36), ForeignKey("collaboration_group_conversations.id", ondelete="CASCADE"), nullable=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    client_user_id = Column(String(36), ForeignKey("client_users.id", ondelete="CASCADE"), nullable=True, index=True)
    last_read_message_id = Column(String(36), nullable=True)
    last_read_at = Column(DateTime(timezone=True), nullable=True)
    is_admin = Column(Boolean, nullable=False, default=False)
    is_muted = Column(Boolean, nullable=False, default=False)
    joined_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    group = relationship("CollaborationGroupConversation", back_populates="members")

    __table_args__ = (
        Index("ix_conv_member_user", "conversation_id", "user_id"),
        Index("ix_conv_member_client", "conversation_id", "client_user_id"),
    )


# ── 9. Messages + 10. Versions + 11. Threads ─────────────────────────────────
class CollaborationMessage(Base):
    __tablename__ = "collaboration_messages"

    id = Column(String(36), primary_key=True, default=_uid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = Column(String(36), ForeignKey("collaboration_conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    thread_id = Column(String(36), ForeignKey("collaboration_threads.id", ondelete="SET NULL"), nullable=True, index=True)
    parent_message_id = Column(String(36), ForeignKey("collaboration_messages.id", ondelete="SET NULL"), nullable=True, index=True)

    # Author: either user OR client_user OR bot
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    client_user_id = Column(String(36), ForeignKey("client_users.id", ondelete="SET NULL"), nullable=True, index=True)
    bot_id = Column(String(36), ForeignKey("collaboration_bot_apps.id", ondelete="SET NULL"), nullable=True, index=True)

    type = Column(Enum(MessageType), nullable=False, default=MessageType.text)
    status = Column(Enum(MessageStatus), nullable=False, default=MessageStatus.visible)
    body = Column(Text, nullable=True)  # markdown
    body_html = Column(Text, nullable=True)  # cached rendered html
    metadata_json = Column(JSON, nullable=False, default=dict)  # cards, polls, decisions
    has_attachments = Column(Boolean, nullable=False, default=False)
    is_pinned = Column(Boolean, nullable=False, default=False)
    is_redacted = Column(Boolean, nullable=False, default=False)

    # Linkage to PSA entities
    linked_task_id = Column(String(36), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    linked_ticket_id = Column(String(36), ForeignKey("sd_tickets.id", ondelete="SET NULL"), nullable=True, index=True)
    linked_deliverable_id = Column(String(36), nullable=True, index=True)
    linked_risk_id = Column(String(36), nullable=True, index=True)

    edited_at = Column(DateTime(timezone=True), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    scheduled_for = Column(DateTime(timezone=True), nullable=True, index=True)
    sent_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    __table_args__ = (
        Index("ix_msg_conv_sent", "conversation_id", "sent_at"),
    )


class CollaborationMessageVersion(Base):
    __tablename__ = "collaboration_message_versions"

    id = Column(String(36), primary_key=True, default=_uid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    message_id = Column(String(36), ForeignKey("collaboration_messages.id", ondelete="CASCADE"), nullable=False, index=True)
    body = Column(Text, nullable=True)
    body_html = Column(Text, nullable=True)
    metadata_json = Column(JSON, nullable=False, default=dict)
    edited_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    edited_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CollaborationThread(Base):
    __tablename__ = "collaboration_threads"

    id = Column(String(36), primary_key=True, default=_uid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = Column(String(36), ForeignKey("collaboration_conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    root_message_id = Column(String(36), ForeignKey("collaboration_messages.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    title = Column(String(200), nullable=True)
    reply_count = Column(Integer, nullable=False, default=0)
    last_reply_at = Column(DateTime(timezone=True), nullable=True)
    is_resolved = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ── 12. Reactions + 13. Mentions + 14. Reads ─────────────────────────────────
class CollaborationReaction(Base):
    __tablename__ = "collaboration_reactions"

    id = Column(String(36), primary_key=True, default=_uid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    message_id = Column(String(36), ForeignKey("collaboration_messages.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    client_user_id = Column(String(36), ForeignKey("client_users.id", ondelete="CASCADE"), nullable=True, index=True)
    emoji = Column(String(60), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("message_id", "user_id", "emoji", name="uq_reaction_user"),
        UniqueConstraint("message_id", "client_user_id", "emoji", name="uq_reaction_client"),
    )


class CollaborationMention(Base):
    __tablename__ = "collaboration_mentions"

    id = Column(String(36), primary_key=True, default=_uid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    message_id = Column(String(36), ForeignKey("collaboration_messages.id", ondelete="CASCADE"), nullable=False, index=True)
    mentioned_user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    mentioned_client_user_id = Column(String(36), ForeignKey("client_users.id", ondelete="CASCADE"), nullable=True, index=True)
    mentioned_team_id = Column(String(36), ForeignKey("collaboration_teams.id", ondelete="CASCADE"), nullable=True)
    mentioned_channel_id = Column(String(36), ForeignKey("collaboration_channels.id", ondelete="CASCADE"), nullable=True)
    is_everyone = Column(Boolean, nullable=False, default=False)  # @here / @channel
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CollaborationRead(Base):
    """Per-user latest seen pointer for a conversation."""
    __tablename__ = "collaboration_reads"

    id = Column(String(36), primary_key=True, default=_uid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = Column(String(36), ForeignKey("collaboration_conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    client_user_id = Column(String(36), ForeignKey("client_users.id", ondelete="CASCADE"), nullable=True, index=True)
    last_message_id = Column(String(36), nullable=True)
    last_read_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("conversation_id", "user_id", name="uq_read_user"),
        UniqueConstraint("conversation_id", "client_user_id", name="uq_read_client"),
    )


# ── 15. Attachments + 16. Versions ───────────────────────────────────────────
class CollaborationAttachment(Base):
    __tablename__ = "collaboration_attachments"

    id = Column(String(36), primary_key=True, default=_uid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    message_id = Column(String(36), ForeignKey("collaboration_messages.id", ondelete="CASCADE"), nullable=True, index=True)
    conversation_id = Column(String(36), ForeignKey("collaboration_conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    uploaded_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    uploaded_by_client_id = Column(String(36), ForeignKey("client_users.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(500), nullable=False)
    mime_type = Column(String(160), nullable=True)
    size_bytes = Column(Integer, nullable=False, default=0)
    storage_provider = Column(String(40), nullable=False, default="local")  # local|s3|minio
    storage_key = Column(String(800), nullable=False)
    sha256 = Column(String(64), nullable=True, index=True)
    av_status = Column(String(40), nullable=False, default="pending")  # pending|clean|infected|skipped
    av_scanned_at = Column(DateTime(timezone=True), nullable=True)
    dlp_status = Column(String(40), nullable=False, default="pending")  # pending|allowed|flagged|blocked
    dlp_findings = Column(JSON, nullable=True)
    is_quarantined = Column(Boolean, nullable=False, default=False)
    preview_key = Column(String(800), nullable=True)
    preview_status = Column(String(40), nullable=False, default="none")  # none|pending|ready|failed|skipped
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CollaborationAttachmentVersion(Base):
    __tablename__ = "collaboration_attachment_versions"

    id = Column(String(36), primary_key=True, default=_uid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    attachment_id = Column(String(36), ForeignKey("collaboration_attachments.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    storage_key = Column(String(800), nullable=False)
    size_bytes = Column(Integer, nullable=False, default=0)
    sha256 = Column(String(64), nullable=True)
    uploaded_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("attachment_id", "version", name="uq_attachment_version"),)


# ── 17/18/19/20. Calls + Participants + Recordings + Transcripts ─────────────
class CollaborationCall(Base):
    __tablename__ = "collaboration_calls"

    id = Column(String(36), primary_key=True, default=_uid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = Column(String(36), ForeignKey("collaboration_conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    initiated_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    kind = Column(Enum(CallKind), nullable=False, default=CallKind.video)
    status = Column(Enum(CallStatus), nullable=False, default=CallStatus.ringing)
    livekit_room = Column(String(160), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Integer, nullable=False, default=0)
    is_recorded = Column(Boolean, nullable=False, default=False)
    has_transcript = Column(Boolean, nullable=False, default=False)
    has_summary = Column(Boolean, nullable=False, default=False)
    metadata_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CollaborationCallParticipant(Base):
    __tablename__ = "collaboration_call_participants"

    id = Column(String(36), primary_key=True, default=_uid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    call_id = Column(String(36), ForeignKey("collaboration_calls.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    client_user_id = Column(String(36), ForeignKey("client_users.id", ondelete="SET NULL"), nullable=True, index=True)
    joined_at = Column(DateTime(timezone=True), nullable=True)
    left_at = Column(DateTime(timezone=True), nullable=True)
    role = Column(String(20), nullable=False, default="participant")  # host | moderator | participant
    is_speaker = Column(Boolean, nullable=False, default=True)
    network_quality = Column(String(20), nullable=True)


class CollaborationRecording(Base):
    __tablename__ = "collaboration_recordings"

    id = Column(String(36), primary_key=True, default=_uid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    call_id = Column(String(36), ForeignKey("collaboration_calls.id", ondelete="CASCADE"), nullable=False, index=True)
    storage_provider = Column(String(40), nullable=False, default="local")
    storage_key = Column(String(800), nullable=False)
    duration_seconds = Column(Integer, nullable=False, default=0)
    size_bytes = Column(Integer, nullable=False, default=0)
    started_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(40), nullable=False, default="processing")  # processing|ready|failed
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CollaborationTranscript(Base):
    __tablename__ = "collaboration_transcripts"

    id = Column(String(36), primary_key=True, default=_uid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    call_id = Column(String(36), ForeignKey("collaboration_calls.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    language = Column(String(20), nullable=False, default="es")
    text = Column(Text, nullable=False, default="")
    segments_json = Column(JSON, nullable=False, default=list)
    summary = Column(Text, nullable=True)
    actions_json = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ── 21. Notifications + 22. Presence ─────────────────────────────────────────
class CollaborationNotification(Base):
    __tablename__ = "collaboration_notifications"

    id = Column(String(36), primary_key=True, default=_uid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    client_user_id = Column(String(36), ForeignKey("client_users.id", ondelete="CASCADE"), nullable=True, index=True)
    kind = Column(Enum(NotificationKind), nullable=False, default=NotificationKind.message)
    conversation_id = Column(String(36), ForeignKey("collaboration_conversations.id", ondelete="CASCADE"), nullable=True, index=True)
    message_id = Column(String(36), ForeignKey("collaboration_messages.id", ondelete="CASCADE"), nullable=True)
    title = Column(String(200), nullable=False)
    body = Column(Text, nullable=True)
    payload = Column(JSON, nullable=False, default=dict)
    is_read = Column(Boolean, nullable=False, default=False, index=True)
    delivered_email = Column(Boolean, nullable=False, default=False)
    delivered_push = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    read_at = Column(DateTime(timezone=True), nullable=True)


class CollaborationPresenceState(Base):
    __tablename__ = "collaboration_presence_states"

    id = Column(String(36), primary_key=True, default=_uid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, unique=True, index=True)
    client_user_id = Column(String(36), ForeignKey("client_users.id", ondelete="CASCADE"), nullable=True, unique=True, index=True)
    status = Column(Enum(PresenceStatus), nullable=False, default=PresenceStatus.offline)
    custom_message = Column(String(200), nullable=True)
    is_in_call = Column(Boolean, nullable=False, default=False)
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


# ── 23. Integrations + 24. Webhooks + 25. Bot apps ───────────────────────────
class CollaborationIntegration(Base):
    __tablename__ = "collaboration_integrations"

    id = Column(String(36), primary_key=True, default=_uid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id = Column(String(36), ForeignKey("collaboration_workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = Column(Enum(IntegrationKind), nullable=False)
    name = Column(String(120), nullable=False)
    is_enabled = Column(Boolean, nullable=False, default=True)
    config = Column(JSON, nullable=False, default=dict)
    secret_ref = Column(String(160), nullable=True)  # reference to secret store (KMS)
    access_token_enc = Column(Text, nullable=True)
    refresh_token_enc = Column(Text, nullable=True)
    token_expires_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class CollaborationWebhook(Base):
    __tablename__ = "collaboration_webhooks"

    id = Column(String(36), primary_key=True, default=_uid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id = Column(String(36), ForeignKey("collaboration_workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    direction = Column(String(20), nullable=False)  # incoming | outgoing
    name = Column(String(120), nullable=False)
    url = Column(String(800), nullable=True)
    secret_token = Column(String(160), nullable=False, default=_uid)
    target_channel_id = Column(String(36), ForeignKey("collaboration_channels.id", ondelete="SET NULL"), nullable=True)
    events = Column(JSON, nullable=False, default=list)  # ['message.created', 'channel.created', ...]
    is_active = Column(Boolean, nullable=False, default=True)
    last_called_at = Column(DateTime(timezone=True), nullable=True)
    failure_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CollaborationBotApp(Base):
    __tablename__ = "collaboration_bot_apps"

    id = Column(String(36), primary_key=True, default=_uid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id = Column(String(36), ForeignKey("collaboration_workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = Column(Enum(BotKind), nullable=False)
    handle = Column(String(60), nullable=False)  # e.g. "nexus", "oracle"
    display_name = Column(String(120), nullable=False)
    description = Column(Text, nullable=True)
    avatar_url = Column(String(500), nullable=True)
    is_enabled = Column(Boolean, nullable=False, default=True)
    permissions = Column(JSON, nullable=False, default=list)
    config = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("workspace_id", "handle", name="uq_bot_handle_workspace"),)


# ── 26. Moderation + 27. Retention + 28. Legal hold + 29. Audit ──────────────
class CollaborationModerationCase(Base):
    __tablename__ = "collaboration_moderation_cases"

    id = Column(String(36), primary_key=True, default=_uid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    message_id = Column(String(36), ForeignKey("collaboration_messages.id", ondelete="CASCADE"), nullable=True, index=True)
    attachment_id = Column(String(36), ForeignKey("collaboration_attachments.id", ondelete="CASCADE"), nullable=True, index=True)
    reason = Column(String(40), nullable=False)  # av | dlp | reported | banned_word
    findings = Column(JSON, nullable=False, default=dict)
    verdict = Column(Enum(ModerationVerdict), nullable=False, default=ModerationVerdict.pending)
    reviewer_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CollaborationRetentionPolicy(Base):
    __tablename__ = "collaboration_retention_policies"

    id = Column(String(36), primary_key=True, default=_uid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id = Column(String(36), ForeignKey("collaboration_workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    scope = Column(String(40), nullable=False, default="workspace")  # workspace | team | channel | type
    target_id = Column(String(36), nullable=True)  # team_id / channel_id / type
    retention_months = Column(Integer, nullable=False, default=24)
    apply_to = Column(String(40), nullable=False, default="all")  # all | messages | attachments | calls
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CollaborationLegalHold(Base):
    __tablename__ = "collaboration_legal_holds"

    id = Column(String(36), primary_key=True, default=_uid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    case_reference = Column(String(120), nullable=False, index=True)
    description = Column(Text, nullable=True)
    custodian_user_ids = Column(JSON, nullable=False, default=list)
    custodian_client_ids = Column(JSON, nullable=False, default=list)
    channel_ids = Column(JSON, nullable=False, default=list)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class CollaborationAuditEvent(Base):
    """Append-only audit log."""
    __tablename__ = "collaboration_audit_events"

    id = Column(String(36), primary_key=True, default=_uid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    actor_client_id = Column(String(36), ForeignKey("client_users.id", ondelete="SET NULL"), nullable=True)
    action = Column(String(80), nullable=False, index=True)
    entity_type = Column(String(60), nullable=False, index=True)
    entity_id = Column(String(36), nullable=True, index=True)
    payload = Column(JSON, nullable=False, default=dict)
    ip_address = Column(String(60), nullable=True)
    user_agent = Column(String(500), nullable=True)
    integrity_hash = Column(String(64), nullable=True)
    prev_event_id = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)


# ── Extras (functional from the doc, not in the 28-list) ─────────────────────
class CollaborationPinnedMessage(Base):
    __tablename__ = "collaboration_pinned_messages"

    id = Column(String(36), primary_key=True, default=_uid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = Column(String(36), ForeignKey("collaboration_conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    message_id = Column(String(36), ForeignKey("collaboration_messages.id", ondelete="CASCADE"), nullable=False, index=True)
    pinned_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    pinned_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("conversation_id", "message_id", name="uq_pin_message"),)


class CollaborationSavedMessage(Base):
    __tablename__ = "collaboration_saved_messages"

    id = Column(String(36), primary_key=True, default=_uid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    message_id = Column(String(36), ForeignKey("collaboration_messages.id", ondelete="CASCADE"), nullable=False, index=True)
    note = Column(Text, nullable=True)
    saved_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "message_id", name="uq_saved_per_user"),)


class CollaborationDraft(Base):
    __tablename__ = "collaboration_drafts"

    id = Column(String(36), primary_key=True, default=_uid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = Column(String(36), ForeignKey("collaboration_conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_message_id = Column(String(36), ForeignKey("collaboration_messages.id", ondelete="SET NULL"), nullable=True)
    body = Column(Text, nullable=False, default="")
    metadata_json = Column(JSON, nullable=False, default=dict)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "conversation_id", "parent_message_id", name="uq_draft"),)


class CollaborationNotificationRule(Base):
    __tablename__ = "collaboration_notification_rules"

    id = Column(String(36), primary_key=True, default=_uid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    scope = Column(String(20), nullable=False, default="global")  # global|workspace|channel|conversation
    target_id = Column(String(36), nullable=True)
    notify_messages = Column(String(20), nullable=False, default="all")  # all|mentions|none
    desktop_push = Column(Boolean, nullable=False, default=True)
    email_digest = Column(String(20), nullable=False, default="weekly")  # off|daily|weekly
    do_not_disturb_from = Column(String(8), nullable=True)  # HH:MM
    do_not_disturb_to = Column(String(8), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class CollaborationBotExecution(Base):
    __tablename__ = "collaboration_bot_executions"

    id = Column(String(36), primary_key=True, default=_uid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    bot_id = Column(String(36), ForeignKey("collaboration_bot_apps.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = Column(String(36), ForeignKey("collaboration_conversations.id", ondelete="SET NULL"), nullable=True, index=True)
    triggered_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    command = Column(String(80), nullable=True)
    input_payload = Column(JSON, nullable=False, default=dict)
    output_payload = Column(JSON, nullable=False, default=dict)
    status = Column(String(40), nullable=False, default="ok")  # ok|error|partial
    duration_ms = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)


class CollaborationSavedSearch(Base):
    __tablename__ = "collaboration_saved_searches"

    id = Column(String(36), primary_key=True, default=_uid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    query = Column(String(500), nullable=False)
    parsed = Column(JSON, nullable=False, default=dict)
    is_pinned = Column(Boolean, nullable=False, default=False)
    use_count = Column(Integer, nullable=False, default=0)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CollaborationPushSubscription(Base):
    __tablename__ = "collaboration_push_subscriptions"

    id = Column(String(36), primary_key=True, default=_uid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    client_user_id = Column(String(36), ForeignKey("client_users.id", ondelete="CASCADE"), nullable=True, index=True)
    endpoint = Column(String(800), nullable=False, unique=True)
    p256dh_key = Column(String(255), nullable=False)
    auth_key = Column(String(255), nullable=False)
    user_agent = Column(String(255), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CollaborationSlashCommandLog(Base):
    __tablename__ = "collaboration_slash_command_logs"

    id = Column(String(36), primary_key=True, default=_uid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    conversation_id = Column(String(36), ForeignKey("collaboration_conversations.id", ondelete="SET NULL"), nullable=True, index=True)
    command = Column(String(60), nullable=False, index=True)
    args = Column(Text, nullable=True)
    success = Column(Boolean, nullable=False, default=True)
    response = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# Convenience export of all models for migrations
__all__ = [
    "ConversationKind", "ChannelType", "TeamRole", "ChannelRole",
    "MessageType", "MessageStatus", "ReactionEmoji",
    "CallKind", "CallStatus", "PresenceStatus",
    "NotificationKind", "ModerationVerdict",
    "IntegrationKind", "BotKind",
    "CollaborationWorkspace", "CollaborationTeam", "CollaborationTeamMember",
    "CollaborationConversation",
    "CollaborationChannel", "CollaborationChannelMember",
    "CollaborationDirectConversation", "CollaborationGroupConversation",
    "CollaborationConversationMember",
    "CollaborationMessage", "CollaborationMessageVersion", "CollaborationThread",
    "CollaborationReaction", "CollaborationMention", "CollaborationRead",
    "CollaborationAttachment", "CollaborationAttachmentVersion",
    "CollaborationCall", "CollaborationCallParticipant",
    "CollaborationRecording", "CollaborationTranscript",
    "CollaborationNotification", "CollaborationPresenceState",
    "CollaborationIntegration", "CollaborationWebhook", "CollaborationBotApp",
    "CollaborationModerationCase", "CollaborationRetentionPolicy",
    "CollaborationLegalHold", "CollaborationAuditEvent",
    "CollaborationPinnedMessage", "CollaborationSavedMessage",
    "CollaborationDraft", "CollaborationNotificationRule",
    "CollaborationBotExecution", "CollaborationSlashCommandLog",
    "CollaborationSavedSearch", "CollaborationPushSubscription",
]

# Avoid unused-import warning for LargeBinary if compatibility imports change.
_ = LargeBinary
