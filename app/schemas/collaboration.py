"""Pydantic schemas for collaboration domain."""
from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field


# ── Common ───────────────────────────────────────────────────────────────────
class Page(BaseModel):
    items: list = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 50


# ── Workspaces ───────────────────────────────────────────────────────────────
class WorkspaceOut(BaseModel):
    id: str
    organization_id: str
    name: str
    icon_url: Optional[str] = None
    primary_color: Optional[str] = None
    settings: dict = {}
    is_active: bool = True


class WorkspaceUpdate(BaseModel):
    name: Optional[str] = None
    icon_url: Optional[str] = None
    primary_color: Optional[str] = None
    settings: Optional[dict] = None


# ── Teams ────────────────────────────────────────────────────────────────────
class TeamCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    slug: Optional[str] = None
    description: Optional[str] = None
    is_private: bool = False
    project_id: Optional[str] = None


class TeamUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_private: Optional[bool] = None
    is_archived: Optional[bool] = None


class TeamOut(BaseModel):
    id: str
    name: str
    slug: str
    description: Optional[str] = None
    is_private: bool
    project_id: Optional[str] = None
    is_archived: bool
    member_count: int = 0
    channel_count: int = 0
    created_at: Optional[datetime] = None


class TeamMemberOut(BaseModel):
    id: str
    user_id: str
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    role: str = "member"
    joined_at: Optional[datetime] = None


class TeamMemberUpsert(BaseModel):
    user_ids: List[str]
    role: str = "member"


# ── Channels ─────────────────────────────────────────────────────────────────
class ChannelCreate(BaseModel):
    team_id: str
    name: str = Field(..., min_length=1, max_length=120)
    slug: Optional[str] = None
    topic: Optional[str] = None
    description: Optional[str] = None
    channel_type: str = "public"  # public|private|announcement|project
    is_default: bool = False
    project_id: Optional[str] = None
    initial_member_ids: List[str] = []


class ChannelUpdate(BaseModel):
    name: Optional[str] = None
    topic: Optional[str] = None
    description: Optional[str] = None
    channel_type: Optional[str] = None
    is_archived: Optional[bool] = None


class ChannelOut(BaseModel):
    id: str
    conversation_id: str
    team_id: str
    name: str
    slug: str
    topic: Optional[str] = None
    description: Optional[str] = None
    channel_type: str
    is_default: bool
    is_archived: bool
    project_id: Optional[str] = None
    member_count: int = 0
    unread_count: int = 0
    last_activity_at: Optional[datetime] = None


class ChannelMemberOut(BaseModel):
    id: str
    user_id: str
    user_name: Optional[str] = None
    role: str = "member"
    notify_level: str = "all"
    is_starred: bool = False
    is_muted: bool = False
    last_read_at: Optional[datetime] = None


# ── Direct + Group Conversations ─────────────────────────────────────────────
class DirectOpenIn(BaseModel):
    user_id: Optional[str] = None
    client_user_id: Optional[str] = None


class GroupCreate(BaseModel):
    title: Optional[str] = None
    user_ids: List[str] = []
    client_user_ids: List[str] = []


class GroupUpdate(BaseModel):
    title: Optional[str] = None
    icon_url: Optional[str] = None


class ConversationOut(BaseModel):
    id: str
    kind: str  # channel|direct|group
    workspace_id: str
    last_activity_at: Optional[datetime] = None
    last_message_id: Optional[str] = None
    is_archived: bool
    title: Optional[str] = None
    icon_url: Optional[str] = None
    members: List[dict] = []
    unread_count: int = 0
    extra: dict = {}


# ── Messages ─────────────────────────────────────────────────────────────────
class MessageCreate(BaseModel):
    conversation_id: Optional[str] = None
    channel_id: Optional[str] = None
    direct_id: Optional[str] = None
    group_id: Optional[str] = None
    parent_message_id: Optional[str] = None
    body: str = Field(..., min_length=1, max_length=20000)
    type: str = "text"
    metadata_json: dict = {}
    mention_user_ids: List[str] = []
    mention_client_ids: List[str] = []
    is_everyone: bool = False
    scheduled_for: Optional[datetime] = None
    linked_task_id: Optional[str] = None
    linked_ticket_id: Optional[str] = None


class MessageUpdate(BaseModel):
    body: Optional[str] = None
    metadata_json: Optional[dict] = None


class MessageOut(BaseModel):
    id: str
    conversation_id: str
    thread_id: Optional[str] = None
    parent_message_id: Optional[str] = None
    user_id: Optional[str] = None
    client_user_id: Optional[str] = None
    bot_id: Optional[str] = None
    author_name: Optional[str] = None
    author_avatar: Optional[str] = None
    type: str
    status: str
    body: Optional[str] = None
    body_html: Optional[str] = None
    metadata_json: dict = {}
    has_attachments: bool = False
    attachments: List[dict] = []
    reactions: List[dict] = []
    is_pinned: bool = False
    is_redacted: bool = False
    linked_task_id: Optional[str] = None
    linked_ticket_id: Optional[str] = None
    edited_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    sent_at: datetime


class MessageVersionOut(BaseModel):
    id: str
    body: Optional[str] = None
    edited_by_user_id: Optional[str] = None
    edited_at: datetime


# ── Reactions / Mentions / Reads ─────────────────────────────────────────────
class ReactionToggle(BaseModel):
    emoji: str = Field(..., min_length=1, max_length=60)


class ReadUpdate(BaseModel):
    last_message_id: str


# ── Pinned + Saved ───────────────────────────────────────────────────────────
class PinIn(BaseModel):
    message_id: str


class SaveIn(BaseModel):
    message_id: str
    note: Optional[str] = None


# ── Drafts ───────────────────────────────────────────────────────────────────
class DraftIn(BaseModel):
    body: str = ""
    metadata_json: dict = {}
    parent_message_id: Optional[str] = None


# ── Presence ─────────────────────────────────────────────────────────────────
class PresenceIn(BaseModel):
    status: str = "online"
    custom_message: Optional[str] = None


class PresenceOut(BaseModel):
    user_id: Optional[str] = None
    client_user_id: Optional[str] = None
    status: str
    custom_message: Optional[str] = None
    is_in_call: bool = False
    last_seen_at: Optional[datetime] = None


# ── Notification rules ───────────────────────────────────────────────────────
class NotificationRuleIn(BaseModel):
    scope: str = "global"
    target_id: Optional[str] = None
    notify_messages: str = "all"
    desktop_push: bool = True
    email_digest: str = "weekly"
    do_not_disturb_from: Optional[str] = None
    do_not_disturb_to: Optional[str] = None


# ── Attachments ──────────────────────────────────────────────────────────────
class AttachmentInitIn(BaseModel):
    conversation_id: str
    name: str
    mime_type: Optional[str] = None
    size_bytes: int = 0


class AttachmentInitOut(BaseModel):
    attachment_id: str
    upload_url: str
    storage_provider: str
    expires_in: int = 3600


class AttachmentOut(BaseModel):
    id: str
    name: str
    mime_type: Optional[str] = None
    size_bytes: int
    storage_provider: str
    av_status: str
    dlp_status: str
    is_quarantined: bool
    download_url: Optional[str] = None
    preview_url: Optional[str] = None
    created_at: datetime


# ── Calls ────────────────────────────────────────────────────────────────────
class CallStartIn(BaseModel):
    conversation_id: str
    kind: str = "video"
    invite_user_ids: List[str] = []


class CallTokenOut(BaseModel):
    call_id: str
    livekit_url: str
    livekit_room: str
    livekit_token: str
    kind: str
    role: str = "participant"


class CallSummaryOut(BaseModel):
    id: str
    conversation_id: str
    kind: str
    status: str
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_seconds: int
    is_recorded: bool
    has_transcript: bool
    has_summary: bool
    summary_text: Optional[str] = None
    actions: List[dict] = []
    participants: List[dict] = []


# ── Bots ─────────────────────────────────────────────────────────────────────
class BotOut(BaseModel):
    id: str
    kind: str
    handle: str
    display_name: str
    description: Optional[str] = None
    avatar_url: Optional[str] = None
    is_enabled: bool


class BotMessageIn(BaseModel):
    bot_handle: str
    conversation_id: str
    args: str = ""


# ── Slash command ────────────────────────────────────────────────────────────
class SlashCommandIn(BaseModel):
    conversation_id: str
    command: str
    args: str = ""


class SlashCommandOut(BaseModel):
    command: str
    success: bool
    response: dict = {}


# ── Integrations / Webhooks ──────────────────────────────────────────────────
class IntegrationCreate(BaseModel):
    kind: str
    name: str
    config: dict = {}


class IntegrationOut(BaseModel):
    id: str
    kind: str
    name: str
    is_enabled: bool
    config: dict
    created_at: datetime


class WebhookCreate(BaseModel):
    direction: str = "incoming"
    name: str
    url: Optional[str] = None
    target_channel_id: Optional[str] = None
    events: List[str] = []


class WebhookOut(BaseModel):
    id: str
    direction: str
    name: str
    url: Optional[str] = None
    secret_token: str
    target_channel_id: Optional[str] = None
    events: List[str] = []
    is_active: bool
    last_called_at: Optional[datetime] = None
    failure_count: int = 0


# ── Compliance ───────────────────────────────────────────────────────────────
class RetentionPolicyIn(BaseModel):
    name: str
    scope: str = "workspace"
    target_id: Optional[str] = None
    retention_months: int = 24
    apply_to: str = "all"


class RetentionPolicyOut(RetentionPolicyIn):
    id: str
    is_active: bool


class LegalHoldIn(BaseModel):
    case_reference: str
    description: Optional[str] = None
    custodian_user_ids: List[str] = []
    custodian_client_ids: List[str] = []
    channel_ids: List[str] = []


class LegalHoldOut(LegalHoldIn):
    id: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    is_active: bool


class EDiscoveryRequest(BaseModel):
    case_reference: Optional[str] = None
    user_ids: List[str] = []
    keywords: List[str] = []
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    include_attachments: bool = True


# ── Search ───────────────────────────────────────────────────────────────────
class SearchHit(BaseModel):
    kind: str  # message|file|channel|user
    id: str
    title: Optional[str] = None
    snippet: Optional[str] = None
    conversation_id: Optional[str] = None
    sent_at: Optional[datetime] = None
    score: float = 0.0
    extra: dict = {}


class SearchResponse(BaseModel):
    hits: List[SearchHit]
    total: int


# ── WebSocket events ─────────────────────────────────────────────────────────
class WsEvent(BaseModel):
    type: str
    payload: dict = {}
    conversation_id: Optional[str] = None
    message_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ── Audit ────────────────────────────────────────────────────────────────────
class AuditEventOut(BaseModel):
    id: str
    actor_user_id: Optional[str] = None
    action: str
    entity_type: str
    entity_id: Optional[str] = None
    payload: dict = {}
    created_at: datetime
