import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from app.core.timeutil import utcnow
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.core.events import emit_event
from app.models.billing_reports import ApprovalRequest
from app.models.client_portal import ClientMessage, ClientUser
from app.models.clients import Client
from app.models.portal_conversations import (
    PortalConversation,
    PortalConversationAssignmentMode,
    PortalConversationAudit,
    PortalConversationClassification,
    PortalConversationGRCStatus,
    PortalConversationMessage,
    PortalConversationMessageType,
    PortalConversationParticipant,
    PortalConversationParticipantType,
    PortalConversationPolicy,
    PortalConversationRole,
    PortalConversationSource,
    PortalConversationStatus,
)
from app.models.project import Project
from app.models.service_desk import AgentGroup, AgentGroupMember, KBArticle, KBStatus
from app.models.user import User
from app.services.notifications import notify_user
import logging

logger = logging.getLogger(__name__)

SENSITIVE_EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
SENSITIVE_TOKEN_RE = re.compile(r"\b[A-Z0-9]{16,}\b", re.IGNORECASE)
SENSITIVE_DIGITS_RE = re.compile(r"\b\d{9,}\b")

DEFAULT_POLICY_MAP = {
    "general": {
        "requires_client_message_approval": False,
        "requires_team_message_approval": False,
        "redact_sensitive_content": True,
        "allow_legacy_federation": True,
        "assignment_mode": "owner_based",
        "first_response_hours": 8,
        "escalation_hours": 24,
        "sensitive_keywords": ["password", "secret", "token", "api_key"],
    },
    "project": {
        "requires_client_message_approval": False,
        "requires_team_message_approval": False,
        "redact_sensitive_content": True,
        "allow_legacy_federation": True,
        "assignment_mode": "owner_based",
        "first_response_hours": 4,
        "escalation_hours": 12,
        "sensitive_keywords": ["password", "token", "api_key"],
    },
    "billing": {
        "requires_client_message_approval": False,
        "requires_team_message_approval": True,
        "redact_sensitive_content": True,
        "allow_legacy_federation": True,
        "assignment_mode": "role_pool",
        "default_role_key": "admin",
        "approval_role_key": "admin",
        "first_response_hours": 4,
        "escalation_hours": 8,
        "sensitive_keywords": ["iban", "invoice", "payment", "bank"],
    },
    "security": {
        "requires_client_message_approval": True,
        "requires_team_message_approval": True,
        "redact_sensitive_content": True,
        "allow_legacy_federation": False,
        "assignment_mode": "role_pool",
        "default_role_key": "admin",
        "approval_role_key": "admin",
        "first_response_hours": 1,
        "escalation_hours": 2,
        "sensitive_keywords": ["password", "secret", "token", "credential", "mfa", "security"],
    },
    "governance": {
        "requires_client_message_approval": True,
        "requires_team_message_approval": True,
        "redact_sensitive_content": True,
        "allow_legacy_federation": False,
        "assignment_mode": "role_pool",
        "default_role_key": "admin",
        "approval_role_key": "admin",
        "first_response_hours": 4,
        "escalation_hours": 8,
        "sensitive_keywords": ["audit", "compliance", "policy", "sod", "gdpr"],
    },
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_past(dt: Optional[datetime]) -> bool:
    if not dt:
        return False
    # SQLite may return naive datetimes even for timezone-aware columns.
    if dt.tzinfo is None:
        return dt < utcnow()
    return dt < _now()


def _enum_value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _legacy_conversation_id(thread_id: str) -> str:
    return f"legacy:{thread_id}"


def _is_legacy_conversation_id(conversation_id: str) -> bool:
    return conversation_id.startswith("legacy:")


def _legacy_thread_key(conversation_id: str) -> str:
    return conversation_id.split(":", 1)[1]


def _policy_defaults(topic_type: str) -> dict:
    return DEFAULT_POLICY_MAP.get(topic_type, DEFAULT_POLICY_MAP["general"]).copy()


def _get_or_create_policy(org_id: str, topic_type: str, db: Session) -> PortalConversationPolicy:
    policy = db.query(PortalConversationPolicy).filter(
        PortalConversationPolicy.organization_id == org_id,
        PortalConversationPolicy.topic_type == topic_type,
    ).first()
    if policy:
        return policy
    defaults = _policy_defaults(topic_type)
    policy = PortalConversationPolicy(
        organization_id=org_id,
        topic_type=topic_type,
        is_active=True,
        requires_client_message_approval=defaults["requires_client_message_approval"],
        requires_team_message_approval=defaults["requires_team_message_approval"],
        redact_sensitive_content=defaults["redact_sensitive_content"],
        allow_legacy_federation=defaults["allow_legacy_federation"],
        assignment_mode=PortalConversationAssignmentMode(defaults["assignment_mode"]),
        default_group_id=defaults.get("default_group_id"),
        default_role_key=defaults.get("default_role_key"),
        first_response_hours=defaults["first_response_hours"],
        escalation_hours=defaults["escalation_hours"],
        approval_role_key=defaults.get("approval_role_key"),
        sensitive_keywords=json.dumps(defaults.get("sensitive_keywords", []), ensure_ascii=False),
    )
    db.add(policy)
    db.flush()
    return policy


def _policy_out(policy: PortalConversationPolicy) -> dict:
    return {
        "id": policy.id,
        "organization_id": policy.organization_id,
        "topic_type": policy.topic_type,
        "is_active": policy.is_active,
        "requires_client_message_approval": policy.requires_client_message_approval,
        "requires_team_message_approval": policy.requires_team_message_approval,
        "redact_sensitive_content": policy.redact_sensitive_content,
        "allow_legacy_federation": policy.allow_legacy_federation,
        "assignment_mode": _enum_value(policy.assignment_mode),
        "default_group_id": policy.default_group_id,
        "default_role_key": policy.default_role_key,
        "first_response_hours": policy.first_response_hours,
        "escalation_hours": policy.escalation_hours,
        "approval_role_key": policy.approval_role_key,
        "approval_user_id": policy.approval_user_id,
        "sensitive_keywords": json.loads(policy.sensitive_keywords or "[]"),
    }


def list_policies(current_user, db: Session) -> list:
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        return []
    for topic_type in DEFAULT_POLICY_MAP:
        _get_or_create_policy(org_id, topic_type, db)
    db.commit()
    policies = db.query(PortalConversationPolicy).filter(
        PortalConversationPolicy.organization_id == org_id
    ).order_by(PortalConversationPolicy.topic_type).all()
    return [_policy_out(policy) for policy in policies]


def update_policy(topic_type: str, payload: dict, current_user, db: Session) -> dict:
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise ValueError("No se pudo resolver organization_id")
    policy = _get_or_create_policy(org_id, topic_type, db)
    for field in [
        "is_active",
        "requires_client_message_approval",
        "requires_team_message_approval",
        "redact_sensitive_content",
        "allow_legacy_federation",
        "default_group_id",
        "default_role_key",
        "first_response_hours",
        "escalation_hours",
        "approval_role_key",
        "approval_user_id",
    ]:
        if field in payload:
            setattr(policy, field, payload[field])
    if payload.get("assignment_mode"):
        policy.assignment_mode = PortalConversationAssignmentMode(payload["assignment_mode"])
    if "sensitive_keywords" in payload:
        policy.sensitive_keywords = json.dumps(payload["sensitive_keywords"] or [], ensure_ascii=False)
    db.commit()
    return _policy_out(policy)


def _participant_out(participant: PortalConversationParticipant) -> dict:
    if participant.user:
        display_name = participant.user.full_name
    elif participant.client_user:
        display_name = participant.client_user.full_name
    elif participant.client_org:
        display_name = participant.client_org.name
    else:
        display_name = participant.role_key or "Participante"
    return {
        "id": participant.id,
        "participant_type": _enum_value(participant.participant_type),
        "user_id": participant.user_id,
        "client_user_id": participant.client_user_id,
        "client_org_id": participant.client_org_id,
        "role_key": participant.role_key,
        "role_in_conversation": _enum_value(participant.role_in_conversation),
        "display_name": display_name,
        "can_read": participant.can_read,
        "can_write": participant.can_write,
        "can_invite": participant.can_invite,
        "can_close": participant.can_close,
        "joined_at": str(participant.joined_at)[:16] if participant.joined_at else None,
        "removed_at": str(participant.removed_at)[:16] if participant.removed_at else None,
    }


def _message_out(message: PortalConversationMessage) -> dict:
    sender_name = "Sistema"
    sender_type = "system"
    if message.sender_user:
        sender_name = message.sender_user.full_name
        sender_type = "team"
    elif message.sender_client:
        sender_name = message.sender_client.full_name
        sender_type = "client"
    return {
        "id": message.id,
        "source": "native",
        "conversation_id": message.conversation_id,
        "project_id": message.project_id,
        "parent_message_id": message.parent_message_id,
        "sender_type": sender_type,
        "sender_name": sender_name,
        "sender_user_id": message.sender_user_id,
        "sender_client_id": message.sender_client_id,
        "message_type": _enum_value(message.message_type),
        "body": message.body,
        "raw_body": message.raw_body,
        "is_internal_note": message.is_internal_note,
        "classification": _enum_value(message.classification),
        "grc_status": _enum_value(message.grc_status),
        "is_redacted": message.is_redacted,
        "moderation_notes": message.moderation_notes,
        "approval_request_id": message.approval_request_id,
        "legacy_message_id": message.legacy_message_id,
        "created_at": str(message.created_at)[:16],
        "delivered_at": str(message.delivered_at)[:16] if message.delivered_at else None,
        "read_at": str(message.read_at)[:16] if message.read_at else None,
    }


def _legacy_message_out(message: ClientMessage) -> dict:
    sender_name = message.sender_client.full_name if message.sender_client else (message.sender_user.full_name if message.sender_user else "Sistema")
    sender_type = "client" if message.sender_client_id else ("team" if message.sender_user_id else "system")
    return {
        "id": message.id,
        "source": "legacy_client_message",
        "conversation_id": _legacy_conversation_id(message.thread_id or message.id),
        "project_id": message.project_id,
        "parent_message_id": message.parent_id,
        "sender_type": sender_type,
        "sender_name": sender_name,
        "sender_user_id": message.sender_user_id,
        "sender_client_id": message.sender_client_id,
        "message_type": "text",
        "body": message.body,
        "raw_body": message.body,
        "is_internal_note": message.is_internal,
        "classification": "public_client" if not message.is_internal else "internal_restricted",
        "grc_status": "allowed",
        "is_redacted": False,
        "moderation_notes": None,
        "approval_request_id": None,
        "legacy_message_id": message.id,
        "created_at": str(message.created_at)[:16],
        "delivered_at": str(message.created_at)[:16] if message.created_at else None,
        "read_at": None,
    }


def _conversation_out(conversation: PortalConversation) -> dict:
    participants = [_participant_out(participant) for participant in conversation.participants if participant.removed_at is None]
    last_message = _message_out(conversation.messages[-1]) if conversation.messages else None
    unread_for_team = sum(1 for message in conversation.messages if message.sender_client_id and not message.read_at and message.grc_status != PortalConversationGRCStatus.blocked)
    unread_for_client = sum(1 for message in conversation.messages if message.sender_user_id and not message.read_at and not message.is_internal_note and message.grc_status != PortalConversationGRCStatus.blocked)
    pending_reviews = sum(1 for message in conversation.messages if message.grc_status == PortalConversationGRCStatus.pending_review)
    is_sla_breached = bool(conversation.first_response_due_at and not conversation.first_response_at and _is_past(conversation.first_response_due_at))
    return {
        "id": conversation.id,
        "source": _enum_value(conversation.source),
        "legacy_thread_id": conversation.legacy_thread_id,
        "organization_id": conversation.organization_id,
        "client_org_id": conversation.client_org_id,
        "project_id": conversation.project_id,
        "topic_type": conversation.topic_type,
        "source_resource_type": conversation.source_resource_type,
        "source_resource_id": conversation.source_resource_id,
        "title": conversation.title,
        "status": _enum_value(conversation.status),
        "assignment_mode": _enum_value(conversation.assignment_mode),
        "visibility_policy_key": conversation.visibility_policy_key,
        "sla_policy_id": conversation.sla_policy_id,
        "policy": _policy_out(conversation.policy) if conversation.policy else None,
        "policy_id": conversation.policy_id,
        "assigned_group_id": conversation.assigned_group_id,
        "assigned_group_name": conversation.assigned_group.name if conversation.assigned_group else None,
        "assigned_role_key": conversation.assigned_role_key,
        "first_response_due_at": str(conversation.first_response_due_at)[:16] if conversation.first_response_due_at else None,
        "first_response_at": str(conversation.first_response_at)[:16] if conversation.first_response_at else None,
        "escalated_at": str(conversation.escalated_at)[:16] if conversation.escalated_at else None,
        "is_sla_breached": is_sla_breached,
        "pending_review_count": pending_reviews,
        "created_by_user_id": conversation.created_by_user_id,
        "created_by_client_id": conversation.created_by_client_id,
        "created_at": str(conversation.created_at)[:16],
        "last_message_at": str(conversation.last_message_at)[:16] if conversation.last_message_at else None,
        "participants": participants,
        "message_count": len(conversation.messages),
        "unread_for_team": unread_for_team,
        "unread_for_client": unread_for_client,
        "last_message": last_message,
    }


def _legacy_conversation_out(root: ClientMessage, replies: list[ClientMessage]) -> dict:
    all_messages = [root, *replies]
    unread_for_team = sum(1 for message in all_messages if message.sender_client_id and not message.is_read_by_team)
    unread_for_client = sum(1 for message in all_messages if message.sender_user_id and not message.is_read_by_client and not message.is_internal)
    last_message = _legacy_message_out(all_messages[-1]) if all_messages else None
    return {
        "id": _legacy_conversation_id(root.thread_id or root.id),
        "source": "legacy_client_message",
        "legacy_thread_id": root.thread_id or root.id,
        "organization_id": root.project.organization_id if root.project else None,
        "client_org_id": root.sender_client.client_org_id if root.sender_client else None,
        "project_id": root.project_id,
        "topic_type": "project",
        "source_resource_type": None,
        "source_resource_id": None,
        "title": root.subject or (root.body[:60] if root.body else "Conversación legacy"),
        "status": "active",
        "assignment_mode": "manual",
        "visibility_policy_key": None,
        "sla_policy_id": None,
        "policy": None,
        "policy_id": None,
        "assigned_group_id": None,
        "assigned_group_name": None,
        "assigned_role_key": None,
        "first_response_due_at": None,
        "first_response_at": None,
        "escalated_at": None,
        "is_sla_breached": False,
        "pending_review_count": 0,
        "created_by_user_id": root.sender_user_id,
        "created_by_client_id": root.sender_client_id,
        "created_at": str(root.created_at)[:16] if root.created_at else None,
        "last_message_at": str(all_messages[-1].created_at)[:16] if all_messages and all_messages[-1].created_at else None,
        "participants": [],
        "message_count": len(all_messages),
        "unread_for_team": unread_for_team,
        "unread_for_client": unread_for_client,
        "last_message": last_message,
    }


def _audit(db: Session, conversation: PortalConversation, action_type: str, *, actor_user_id: Optional[str] = None, actor_client_id: Optional[str] = None, target_type: Optional[str] = None, target_id: Optional[str] = None, status: str = "success", details: Optional[dict] = None) -> None:
    db.add(PortalConversationAudit(
        conversation_id=conversation.id,
        organization_id=conversation.organization_id,
        actor_user_id=actor_user_id,
        actor_client_id=actor_client_id,
        action_type=action_type,
        target_type=target_type,
        target_id=target_id,
        status=status,
        details=json.dumps(details or {}, ensure_ascii=False),
    ))


def _base_conversation_query(db: Session):
    return db.query(PortalConversation).options(
        joinedload(PortalConversation.policy),
        joinedload(PortalConversation.assigned_group),
        joinedload(PortalConversation.participants).joinedload(PortalConversationParticipant.user),
        joinedload(PortalConversation.participants).joinedload(PortalConversationParticipant.client_user),
        joinedload(PortalConversation.participants).joinedload(PortalConversationParticipant.client_org),
        joinedload(PortalConversation.messages).joinedload(PortalConversationMessage.sender_user),
        joinedload(PortalConversation.messages).joinedload(PortalConversationMessage.sender_client),
    )


def _legacy_roots_query(db: Session):
    return db.query(ClientMessage).options(
        joinedload(ClientMessage.sender_client),
        joinedload(ClientMessage.sender_user),
        joinedload(ClientMessage.project),
    ).filter(ClientMessage.parent_id == None)


def _get_project_for_team(project_id: str, current_user, db: Session) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError("Proyecto no encontrado")
    if not getattr(current_user, "is_superadmin", False):
        if not current_user.organization_id or project.organization_id != current_user.organization_id:
            raise ValueError("Proyecto no encontrado")
    if not project.organization_id:
        raise ValueError("Proyecto sin organization_id")
    return project


def _get_team_conversation(conversation_id: str, current_user, db: Session) -> PortalConversation:
    conversation = _base_conversation_query(db).filter(PortalConversation.id == conversation_id).first()
    if not conversation:
        raise ValueError("Conversación no encontrada")
    if not getattr(current_user, "is_superadmin", False) and current_user.organization_id != conversation.organization_id:
        raise ValueError("Conversación no encontrada")
    return conversation


def _get_client_conversation(conversation_id: str, current_client: ClientUser, db: Session) -> PortalConversation:
    conversation = _base_conversation_query(db).filter(PortalConversation.id == conversation_id).first()
    if not conversation:
        raise ValueError("Conversación no encontrada")
    accessible = set(current_client.get_project_ids())
    if conversation.project_id and conversation.project_id not in accessible:
        raise ValueError("Conversación no encontrada")
    allowed = False
    for participant in conversation.participants:
        if participant.removed_at is not None:
            continue
        if participant.client_user_id == current_client.id:
            allowed = True
        if current_client.client_org_id and participant.client_org_id == current_client.client_org_id:
            allowed = True
    if not allowed:
        raise ValueError("Conversación no encontrada")
    return conversation


def _ensure_participant(db: Session, conversation: PortalConversation, *, participant_type: PortalConversationParticipantType, role_in_conversation: PortalConversationRole, user_id: Optional[str] = None, client_user_id: Optional[str] = None, client_org_id: Optional[str] = None, role_key: Optional[str] = None, added_by_user_id: Optional[str] = None, can_invite: bool = False, can_close: bool = False) -> PortalConversationParticipant:
    existing = db.query(PortalConversationParticipant).filter(
        PortalConversationParticipant.conversation_id == conversation.id,
        PortalConversationParticipant.participant_type == participant_type,
        PortalConversationParticipant.user_id == user_id,
        PortalConversationParticipant.client_user_id == client_user_id,
        PortalConversationParticipant.client_org_id == client_org_id,
        PortalConversationParticipant.role_key == role_key,
    ).first()
    if existing:
        existing.removed_at = None
        existing.role_in_conversation = role_in_conversation
        existing.can_read = True
        existing.can_write = True
        existing.can_invite = can_invite
        existing.can_close = can_close
        return existing
    participant = PortalConversationParticipant(
        conversation_id=conversation.id,
        participant_type=participant_type,
        user_id=user_id,
        client_user_id=client_user_id,
        client_org_id=client_org_id,
        role_key=role_key,
        role_in_conversation=role_in_conversation,
        can_read=True,
        can_write=True,
        can_invite=can_invite,
        can_close=can_close,
        added_by_user_id=added_by_user_id,
    )
    db.add(participant)
    return participant


def _resolve_group_members(group_id: str, db: Session) -> list[User]:
    group = db.query(AgentGroup).options(joinedload(AgentGroup.members).joinedload(AgentGroupMember.user)).filter(
        AgentGroup.id == group_id,
        AgentGroup.is_active == True,
    ).first()
    if not group:
        return []
    return [member.user for member in group.members if member.user and member.user.is_active]


def _notify_users(db: Session, user_ids: list[str], title: str, body: str, resource_id: str) -> None:
    seen = set()
    for user_id in user_ids:
        if not user_id or user_id in seen:
            continue
        seen.add(user_id)
        notify_user(
            db,
            user_id,
            "ticket_replied",
            title,
            body,
            resource="portal_conversations",
            resource_id=resource_id,
            action_url=f"/clients?conversation={resource_id}",
        )


def _apply_assignment_policy(conversation: PortalConversation, policy: PortalConversationPolicy, current_actor, db: Session) -> list[str]:
    assigned_user_ids: list[str] = []
    conversation.assignment_mode = policy.assignment_mode
    conversation.assigned_group_id = policy.default_group_id
    conversation.assigned_role_key = policy.default_role_key
    added_by_user_id = getattr(current_actor, "id", None) if isinstance(current_actor, User) else None
    if policy.assignment_mode == PortalConversationAssignmentMode.owner_based and conversation.project_id:
        project = db.query(Project).filter(Project.id == conversation.project_id).first()
        if project and project.pm_id:
            _ensure_participant(
                db,
                conversation,
                participant_type=PortalConversationParticipantType.internal_user,
                user_id=project.pm_id,
                role_in_conversation=PortalConversationRole.owner,
                added_by_user_id=added_by_user_id,
                can_invite=True,
                can_close=True,
            )
            assigned_user_ids.append(project.pm_id)
    elif policy.assignment_mode == PortalConversationAssignmentMode.role_pool and policy.default_group_id:
        for user in _resolve_group_members(policy.default_group_id, db):
            _ensure_participant(
                db,
                conversation,
                participant_type=PortalConversationParticipantType.internal_user,
                user_id=user.id,
                role_in_conversation=PortalConversationRole.agent,
                added_by_user_id=added_by_user_id,
            )
            assigned_user_ids.append(user.id)
    elif policy.assignment_mode == PortalConversationAssignmentMode.role_pool and policy.default_role_key:
        users = db.query(User).filter(
            User.organization_id == conversation.organization_id,
            User.role == policy.default_role_key,
            User.is_active == True,
        ).all()
        for user in users:
            _ensure_participant(
                db,
                conversation,
                participant_type=PortalConversationParticipantType.internal_user,
                user_id=user.id,
                role_in_conversation=PortalConversationRole.agent,
                added_by_user_id=added_by_user_id,
            )
            assigned_user_ids.append(user.id)
    return assigned_user_ids


def _redact_sensitive(text: str, keywords: list[str]) -> tuple[str, bool, list[str]]:
    redacted = text
    notes = []
    if SENSITIVE_EMAIL_RE.search(redacted):
        redacted = SENSITIVE_EMAIL_RE.sub("[REDACTED_EMAIL]", redacted)
        notes.append("email")
    if SENSITIVE_TOKEN_RE.search(redacted):
        redacted = SENSITIVE_TOKEN_RE.sub("[REDACTED_TOKEN]", redacted)
        notes.append("token")
    if SENSITIVE_DIGITS_RE.search(redacted):
        redacted = SENSITIVE_DIGITS_RE.sub("[REDACTED_NUMBER]", redacted)
        notes.append("number")
    for keyword in keywords:
        if keyword.lower() in redacted.lower():
            redacted = re.sub(re.escape(keyword), "[REDACTED_KEYWORD]", redacted, flags=re.IGNORECASE)
            notes.append(keyword.lower())
    return redacted, redacted != text, list(dict.fromkeys(notes))


def _resolve_classification(topic_type: str, is_internal_note: bool, was_redacted: bool) -> PortalConversationClassification:
    if is_internal_note:
        return PortalConversationClassification.internal_restricted
    if topic_type in {"security", "governance", "billing"} or was_redacted:
        return PortalConversationClassification.confidential
    return PortalConversationClassification.public_client


def _approver_candidates(policy: PortalConversationPolicy, conversation: PortalConversation, db: Session) -> list[User]:
    users = []
    seen = set()
    if policy.approval_user_id:
        user = db.query(User).filter(User.id == policy.approval_user_id).first()
        if user:
            users.append(user)
            seen.add(user.id)
    if policy.approval_role_key:
        role_users = db.query(User).filter(
            User.organization_id == conversation.organization_id,
            User.role == policy.approval_role_key,
            User.is_active == True,
        ).all()
        for user in role_users:
            if user.id not in seen:
                users.append(user)
                seen.add(user.id)
    for participant in conversation.participants:
        if participant.removed_at is None and participant.user and participant.role_in_conversation == PortalConversationRole.owner and participant.user.id not in seen:
            users.append(participant.user)
            seen.add(participant.user.id)
    return users


def _create_message_approval_request(message: PortalConversationMessage, conversation: PortalConversation, approvers: list[User], db: Session) -> Optional[str]:
    requester_id = message.sender_user_id
    if not requester_id:
        requester_id = next((participant.user_id for participant in conversation.participants if participant.removed_at is None and participant.user_id), None)
    if not requester_id:
        requester_id = approvers[0].id if approvers else None
    if not requester_id:
        return None
    req = ApprovalRequest(
        id=str(uuid.uuid4()),
        workflow_id=None,
        entity_type="portal_conversation_message",
        entity_id=message.id,
        entity_summary=f"{conversation.title}: {message.body[:120]}",
        requested_by=requester_id,
        current_step=1,
        status="pending",
        step_started_at=_now(),
    )
    db.add(req)
    db.flush()
    return req.id


def _refresh_conversation_status(conversation: PortalConversation) -> None:
    if any(message.grc_status == PortalConversationGRCStatus.pending_review for message in conversation.messages):
        conversation.status = PortalConversationStatus.pending_approval
    elif conversation.status == PortalConversationStatus.pending_approval:
        conversation.status = PortalConversationStatus.active


def _mark_first_response_if_needed(conversation: PortalConversation, sender_type: str) -> None:
    if sender_type == "team" and conversation.first_response_at is None:
        conversation.first_response_at = _now()
    if sender_type == "client":
        hours = conversation.policy.first_response_hours if conversation.policy else 8
        conversation.first_response_at = None
        conversation.first_response_due_at = _now() + timedelta(hours=hours)
        conversation.escalated_at = None


def _apply_message_policy(conversation: PortalConversation, sender_type: str, body: str, is_internal_note: bool, sender_user_id: Optional[str], sender_client_id: Optional[str], parent_message_id: Optional[str], message_type: str, db: Session) -> PortalConversationMessage:
    policy = conversation.policy or _get_or_create_policy(conversation.organization_id, conversation.topic_type, db)
    keywords = json.loads(policy.sensitive_keywords or "[]")
    redacted_body, was_redacted, notes = _redact_sensitive(body.strip(), keywords)
    approval_required = policy.requires_client_message_approval if sender_type == "client" else policy.requires_team_message_approval
    classification = _resolve_classification(conversation.topic_type, is_internal_note, was_redacted)
    effective_body = redacted_body if policy.redact_sensitive_content else body.strip()
    grc_status = PortalConversationGRCStatus.allowed
    moderation_notes = notes[:]
    if approval_required:
        grc_status = PortalConversationGRCStatus.pending_review
        moderation_notes.append("approval_required")
    elif was_redacted:
        grc_status = PortalConversationGRCStatus.redacted
    approvers = _approver_candidates(policy, conversation, db) if grc_status == PortalConversationGRCStatus.pending_review else []
    message = PortalConversationMessage(
        conversation_id=conversation.id,
        organization_id=conversation.organization_id,
        project_id=conversation.project_id,
        parent_message_id=parent_message_id,
        sender_user_id=sender_user_id,
        sender_client_id=sender_client_id,
        message_type=PortalConversationMessageType(message_type),
        body=effective_body,
        raw_body=body.strip(),
        moderation_notes=", ".join(moderation_notes) if moderation_notes else None,
        is_internal_note=is_internal_note,
        is_redacted=was_redacted,
        classification=classification,
        grc_status=grc_status,
        delivered_at=None if grc_status == PortalConversationGRCStatus.pending_review else _now(),
    )
    db.add(message)
    db.flush()
    if grc_status == PortalConversationGRCStatus.pending_review:
        approval_request_id = _create_message_approval_request(message, conversation, approvers, db)
        if approval_request_id:
            message.approval_request_id = approval_request_id
        _notify_users(db, [user.id for user in approvers], f"Aprobación requerida: {conversation.title}", "Hay un mensaje pendiente de revisión en conversaciones del portal.", conversation.id)
    return message


def _get_legacy_thread_for_team(conversation_id: str, current_user, db: Session) -> tuple[ClientMessage, list[ClientMessage]]:
    thread_key = _legacy_thread_key(conversation_id)
    root = _legacy_roots_query(db).filter(ClientMessage.thread_id == thread_key).first()
    if not root:
        root = _legacy_roots_query(db).filter(ClientMessage.id == thread_key).first()
    if not root:
        raise ValueError("Conversación no encontrada")
    if root.project_id:
        _get_project_for_team(root.project_id, current_user, db)
    replies = db.query(ClientMessage).options(
        joinedload(ClientMessage.sender_client),
        joinedload(ClientMessage.sender_user),
        joinedload(ClientMessage.project),
    ).filter(ClientMessage.parent_id == root.id).order_by(ClientMessage.created_at).all()
    return root, replies


def _get_legacy_thread_for_client(conversation_id: str, current_client: ClientUser, db: Session) -> tuple[ClientMessage, list[ClientMessage]]:
    thread_key = _legacy_thread_key(conversation_id)
    root = _legacy_roots_query(db).filter(ClientMessage.thread_id == thread_key).first()
    if not root:
        root = _legacy_roots_query(db).filter(ClientMessage.id == thread_key).first()
    if not root:
        raise ValueError("Conversación no encontrada")
    if root.project_id and root.project_id not in set(current_client.get_project_ids()):
        raise ValueError("Conversación no encontrada")
    if root.sender_client and current_client.client_org_id and root.sender_client.client_org_id and root.sender_client.client_org_id != current_client.client_org_id:
        raise ValueError("Conversación no encontrada")
    replies = db.query(ClientMessage).options(
        joinedload(ClientMessage.sender_client),
        joinedload(ClientMessage.sender_user),
        joinedload(ClientMessage.project),
    ).filter(ClientMessage.parent_id == root.id).order_by(ClientMessage.created_at).all()
    return root, replies


def _list_legacy_threads_for_team(current_user, db: Session, project_id: Optional[str], client_org_id: Optional[str]) -> list:
    query = _legacy_roots_query(db)
    if project_id:
        query = query.filter(ClientMessage.project_id == project_id)
    roots = query.order_by(ClientMessage.created_at.desc()).all()
    result = []
    for root in roots:
        if root.project_id:
            try:
                _get_project_for_team(root.project_id, current_user, db)
            except ValueError:
                continue
        if client_org_id and (not root.sender_client or root.sender_client.client_org_id != client_org_id):
            continue
        replies = db.query(ClientMessage).options(
            joinedload(ClientMessage.sender_client),
            joinedload(ClientMessage.sender_user),
            joinedload(ClientMessage.project),
        ).filter(ClientMessage.parent_id == root.id).order_by(ClientMessage.created_at).all()
        result.append(_legacy_conversation_out(root, replies))
    return result


def _list_legacy_threads_for_client(current_client: ClientUser, db: Session) -> list:
    accessible = set(current_client.get_project_ids())
    roots = _legacy_roots_query(db).order_by(ClientMessage.created_at.desc()).all()
    result = []
    for root in roots:
        if root.project_id and root.project_id not in accessible:
            continue
        if root.sender_client and current_client.client_org_id and root.sender_client.client_org_id and root.sender_client.client_org_id != current_client.client_org_id:
            continue
        replies = db.query(ClientMessage).options(
            joinedload(ClientMessage.sender_client),
            joinedload(ClientMessage.sender_user),
            joinedload(ClientMessage.project),
        ).filter(ClientMessage.parent_id == root.id).order_by(ClientMessage.created_at).all()
        result.append(_legacy_conversation_out(root, replies))
    return result


def list_team_conversations(current_user, db: Session, project_id: Optional[str] = None, client_org_id: Optional[str] = None, assigned_to_me: bool = False) -> list:
    query = _base_conversation_query(db)
    if not getattr(current_user, "is_superadmin", False):
        query = query.filter(PortalConversation.organization_id == current_user.organization_id)
    if project_id:
        query = query.filter(PortalConversation.project_id == project_id)
    if client_org_id:
        query = query.filter(PortalConversation.client_org_id == client_org_id)
    if assigned_to_me:
        query = query.join(PortalConversationParticipant, PortalConversationParticipant.conversation_id == PortalConversation.id).filter(
            PortalConversationParticipant.user_id == current_user.id,
            PortalConversationParticipant.removed_at.is_(None),
        )
    conversations = [_conversation_out(item) for item in query.order_by(PortalConversation.last_message_at.desc().nullslast(), PortalConversation.created_at.desc()).distinct().all()]
    conversations.extend(_list_legacy_threads_for_team(current_user, db, project_id, client_org_id))
    conversations.sort(key=lambda item: item.get("last_message_at") or item.get("created_at") or "", reverse=True)
    return conversations


def list_client_conversations(current_client: ClientUser, db: Session) -> list:
    participant_filters = [PortalConversationParticipant.client_user_id == current_client.id]
    if current_client.client_org_id:
        participant_filters.append(PortalConversationParticipant.client_org_id == current_client.client_org_id)
    query = _base_conversation_query(db).join(
        PortalConversationParticipant,
        PortalConversationParticipant.conversation_id == PortalConversation.id,
    ).filter(
        PortalConversationParticipant.removed_at.is_(None),
        or_(*participant_filters),
    )
    accessible = current_client.get_project_ids()
    if accessible:
        query = query.filter(or_(PortalConversation.project_id == None, PortalConversation.project_id.in_(accessible)))
    conversations = [_conversation_out(item) for item in query.order_by(PortalConversation.last_message_at.desc().nullslast(), PortalConversation.created_at.desc()).distinct().all()]
    conversations.extend(_list_legacy_threads_for_client(current_client, db))
    conversations.sort(key=lambda item: item.get("last_message_at") or item.get("created_at") or "", reverse=True)
    return conversations


def get_team_conversation_detail(conversation_id: str, current_user, db: Session) -> dict:
    if _is_legacy_conversation_id(conversation_id):
        root, replies = _get_legacy_thread_for_team(conversation_id, current_user, db)
        return _legacy_conversation_out(root, replies)
    return _conversation_out(_get_team_conversation(conversation_id, current_user, db))


def get_client_conversation_detail(conversation_id: str, current_client: ClientUser, db: Session) -> dict:
    if _is_legacy_conversation_id(conversation_id):
        root, replies = _get_legacy_thread_for_client(conversation_id, current_client, db)
        return _legacy_conversation_out(root, replies)
    return _conversation_out(_get_client_conversation(conversation_id, current_client, db))


def create_team_conversation(payload, current_user, db: Session) -> dict:
    if not payload.title.strip():
        raise ValueError("El título es obligatorio")
    org_id = current_user.organization_id
    client_org_id = payload.client_org_id
    if payload.project_id:
        project = _get_project_for_team(payload.project_id, current_user, db)
        org_id = project.organization_id
        if not client_org_id:
            client_org_id = project.client_id
    if not org_id:
        raise ValueError("No se pudo resolver organization_id para la conversación")
    if client_org_id and not db.query(Client).filter(Client.id == client_org_id).first():
        raise ValueError("Cliente no encontrado")
    policy = _get_or_create_policy(org_id, payload.topic_type, db)
    conversation = PortalConversation(
        organization_id=org_id,
        client_org_id=client_org_id,
        project_id=payload.project_id,
        topic_type=payload.topic_type,
        source=PortalConversationSource.native,
        source_resource_type=payload.source_resource_type,
        source_resource_id=payload.source_resource_id,
        title=payload.title.strip(),
        status=PortalConversationStatus.active,
        assignment_mode=policy.assignment_mode,
        visibility_policy_key=payload.visibility_policy_key,
        policy_id=policy.id,
        created_by_user_id=current_user.id,
    )
    db.add(conversation)
    db.flush()
    _ensure_participant(db, conversation, participant_type=PortalConversationParticipantType.internal_user, user_id=current_user.id, role_in_conversation=PortalConversationRole.owner, added_by_user_id=current_user.id, can_invite=True, can_close=True)
    for user_id in payload.internal_user_ids:
        _ensure_participant(db, conversation, participant_type=PortalConversationParticipantType.internal_user, user_id=user_id, role_in_conversation=PortalConversationRole.agent, added_by_user_id=current_user.id)
    for client_user_id in payload.client_user_ids:
        _ensure_participant(db, conversation, participant_type=PortalConversationParticipantType.client_user, client_user_id=client_user_id, role_in_conversation=PortalConversationRole.requester, added_by_user_id=current_user.id)
    if conversation.client_org_id:
        _ensure_participant(db, conversation, participant_type=PortalConversationParticipantType.client_org, client_org_id=conversation.client_org_id, role_in_conversation=PortalConversationRole.watcher, added_by_user_id=current_user.id)
    assigned_users = _apply_assignment_policy(conversation, policy, current_user, db)
    _audit(db, conversation, "portal_conversation.created", actor_user_id=current_user.id, details={"topic_type": conversation.topic_type, "project_id": conversation.project_id})
    if assigned_users:
        _notify_users(db, assigned_users, f"Nueva conversación: {conversation.title}", "Se te ha asignado una conversación del portal.", conversation.id)
    db.commit()
    emit_event(db, "portal_conversation.created", {"title": conversation.title, "topic_type": conversation.topic_type}, actor=current_user, org_id=conversation.organization_id, resource_type="portal_conversation", resource_id=conversation.id, project_id=conversation.project_id)
    return get_team_conversation_detail(conversation.id, current_user, db)


def create_client_conversation(payload, current_client: ClientUser, db: Session) -> dict:
    if not payload.title.strip():
        raise ValueError("El título es obligatorio")
    accessible = current_client.get_project_ids()
    project_id = payload.project_id or (accessible[0] if accessible else None)
    if not project_id:
        raise ValueError("Debes indicar un proyecto accesible")
    if project_id not in accessible:
        raise ValueError("No tienes acceso a ese proyecto")
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project or not project.organization_id:
        raise ValueError("Proyecto no encontrado")
    policy = _get_or_create_policy(project.organization_id, payload.topic_type, db)
    conversation = PortalConversation(
        organization_id=project.organization_id,
        client_org_id=current_client.client_org_id or project.client_id,
        project_id=project_id,
        topic_type=payload.topic_type,
        source=PortalConversationSource.native,
        source_resource_type=payload.source_resource_type,
        source_resource_id=payload.source_resource_id,
        title=payload.title.strip(),
        status=PortalConversationStatus.active,
        assignment_mode=policy.assignment_mode,
        visibility_policy_key=payload.visibility_policy_key,
        policy_id=policy.id,
        created_by_client_id=current_client.id,
        first_response_due_at=_now() + timedelta(hours=policy.first_response_hours),
    )
    db.add(conversation)
    db.flush()
    _ensure_participant(db, conversation, participant_type=PortalConversationParticipantType.client_user, client_user_id=current_client.id, role_in_conversation=PortalConversationRole.requester)
    if conversation.client_org_id:
        _ensure_participant(db, conversation, participant_type=PortalConversationParticipantType.client_org, client_org_id=conversation.client_org_id, role_in_conversation=PortalConversationRole.watcher)
    assigned_users = _apply_assignment_policy(conversation, policy, current_client, db)
    _audit(db, conversation, "portal_conversation.created_by_client", actor_client_id=current_client.id, details={"topic_type": conversation.topic_type, "project_id": conversation.project_id})
    if assigned_users:
        _notify_users(db, assigned_users, f"Nueva conversación cliente: {conversation.title}", "El cliente ha abierto una conversación en el portal.", conversation.id)
    db.commit()
    emit_event(db, "portal_conversation.created", {"title": conversation.title, "topic_type": conversation.topic_type}, org_id=conversation.organization_id, resource_type="portal_conversation", resource_id=conversation.id, project_id=conversation.project_id)
    return get_client_conversation_detail(conversation.id, current_client, db)


def list_team_messages(conversation_id: str, current_user, db: Session) -> list:
    if _is_legacy_conversation_id(conversation_id):
        root, replies = _get_legacy_thread_for_team(conversation_id, current_user, db)
        db.query(ClientMessage).filter(ClientMessage.project_id == root.project_id, ClientMessage.sender_client_id != None, ClientMessage.is_read_by_team == False).update({"is_read_by_team": True})
        db.commit()
        return [_legacy_message_out(root)] + [_legacy_message_out(reply) for reply in replies]
    conversation = _get_team_conversation(conversation_id, current_user, db)
    db.query(PortalConversationMessage).filter(PortalConversationMessage.conversation_id == conversation.id, PortalConversationMessage.sender_client_id != None, PortalConversationMessage.read_at == None).update({"read_at": _now()})
    db.commit()
    return [_message_out(message) for message in conversation.messages]


def list_client_messages(conversation_id: str, current_client: ClientUser, db: Session) -> list:
    if _is_legacy_conversation_id(conversation_id):
        root, replies = _get_legacy_thread_for_client(conversation_id, current_client, db)
        accessible = current_client.get_project_ids()
        db.query(ClientMessage).filter(ClientMessage.project_id.in_(accessible) if accessible else ClientMessage.project_id == None, ClientMessage.sender_user_id != None, ClientMessage.is_read_by_client == False).update({"is_read_by_client": True})
        db.commit()
        return [_legacy_message_out(root)] + [_legacy_message_out(reply) for reply in replies if not reply.is_internal]
    conversation = _get_client_conversation(conversation_id, current_client, db)
    db.query(PortalConversationMessage).filter(PortalConversationMessage.conversation_id == conversation.id, PortalConversationMessage.sender_user_id != None, PortalConversationMessage.read_at == None, PortalConversationMessage.is_internal_note == False).update({"read_at": _now()})
    db.commit()
    return [_message_out(message) for message in conversation.messages if not message.is_internal_note and message.grc_status != PortalConversationGRCStatus.blocked]


def send_team_message(conversation_id: str, payload, current_user, db: Session) -> dict:
    if _is_legacy_conversation_id(conversation_id):
        root, _replies = _get_legacy_thread_for_team(conversation_id, current_user, db)
        message = ClientMessage(project_id=root.project_id, sender_user_id=current_user.id, is_read_by_team=True, is_read_by_client=False, subject=None, body=payload.body.strip(), parent_id=root.id, thread_id=root.thread_id or root.id, is_internal=payload.is_internal_note)
        db.add(message)
        db.commit()
        db.refresh(message)
        return _legacy_message_out(message)
    conversation = _get_team_conversation(conversation_id, current_user, db)
    message = _apply_message_policy(conversation, "team", payload.body, payload.is_internal_note, current_user.id, None, payload.parent_message_id, payload.message_type, db)
    conversation.last_message_at = _now()
    _mark_first_response_if_needed(conversation, "team")
    _refresh_conversation_status(conversation)
    _audit(db, conversation, "portal_conversation.message_sent", actor_user_id=current_user.id, target_type="message", target_id=message.id, details={"message_type": _enum_value(message.message_type), "grc_status": _enum_value(message.grc_status)})
    recipient_user_ids = [participant.user_id for participant in conversation.participants if participant.removed_at is None and participant.user_id and participant.user_id != current_user.id]
    if recipient_user_ids and not payload.is_internal_note:
        _notify_users(db, recipient_user_ids, f"Nueva respuesta en {conversation.title}", payload.body[:140], conversation.id)
    db.commit()
    emit_event(db, "portal_conversation.message_sent", {"conversation_id": conversation.id, "message_type": _enum_value(message.message_type)}, actor=current_user, org_id=conversation.organization_id, resource_type="portal_conversation_message", resource_id=message.id, project_id=conversation.project_id)
    return _message_out(message)


def send_client_message(conversation_id: str, payload, current_client: ClientUser, db: Session) -> dict:
    if payload.is_internal_note:
        raise ValueError("El cliente no puede enviar notas internas")
    if _is_legacy_conversation_id(conversation_id):
        root, _replies = _get_legacy_thread_for_client(conversation_id, current_client, db)
        message = ClientMessage(project_id=root.project_id, sender_client_id=current_client.id, is_read_by_team=False, is_read_by_client=True, subject=None, body=payload.body.strip(), parent_id=root.id, thread_id=root.thread_id or root.id, is_internal=False)
        db.add(message)
        db.commit()
        db.refresh(message)
        return _legacy_message_out(message)
    conversation = _get_client_conversation(conversation_id, current_client, db)
    message = _apply_message_policy(conversation, "client", payload.body, False, None, current_client.id, payload.parent_message_id, payload.message_type, db)
    conversation.last_message_at = _now()
    _mark_first_response_if_needed(conversation, "client")
    _refresh_conversation_status(conversation)
    _audit(db, conversation, "portal_conversation.message_sent_by_client", actor_client_id=current_client.id, target_type="message", target_id=message.id, details={"message_type": _enum_value(message.message_type), "grc_status": _enum_value(message.grc_status)})
    recipient_user_ids = [participant.user_id for participant in conversation.participants if participant.removed_at is None and participant.user_id]
    if recipient_user_ids:
        _notify_users(db, recipient_user_ids, f"Mensaje de cliente en {conversation.title}", payload.body[:140], conversation.id)
    db.commit()
    emit_event(db, "portal_conversation.message_sent", {"conversation_id": conversation.id, "message_type": _enum_value(message.message_type)}, org_id=conversation.organization_id, resource_type="portal_conversation_message", resource_id=message.id, project_id=conversation.project_id)
    return _message_out(message)


def send_l1_bot_reply(conversation_id: str, current_client: ClientUser, db: Session) -> dict:
    """Generate and persist a first-line bot reply for a portal conversation.

    Strategy:
    - Reads latest visible client message.
    - Looks up published KB by simple relevance (ILIKE title/body/tags).
    - Responds with guided next steps and optional escalation cue.
    """
    conversation = _get_client_conversation(conversation_id, current_client, db)

    latest_client_msg = (
        db.query(PortalConversationMessage)
        .filter(
            PortalConversationMessage.conversation_id == conversation.id,
            PortalConversationMessage.sender_client_id == current_client.id,
            PortalConversationMessage.is_internal_note == False,
            PortalConversationMessage.grc_status != PortalConversationGRCStatus.blocked,
        )
        .order_by(PortalConversationMessage.created_at.desc())
        .first()
    )

    if not latest_client_msg:
        raise ValueError("No hay mensaje de cliente para que el bot responda")

    query = (latest_client_msg.body or "").strip()
    # Revisión 2026-11: antes buscaba la pregunta ENTERA como subcadena literal
    # (casi nunca casaba). Ahora, la corrección pública de un experto si encaja,
    # si no los artículos públicos relevantes; sin nada, queda como hueco.
    from app.services.service_desk.kb_calidad import buscar_correccion, fuentes, registrar_hueco
    correccion = buscar_correccion(db, query, solo_publica=True)
    citas = [] if correccion else fuentes(db, query, solo_publico=True)

    if correccion:
        correccion.usage_count = (correccion.usage_count or 0) + 1
        correccion.last_used_at = _now()
        answer = ("Soy el asistente L1 del portal. Esto es lo que nuestro equipo indica para esta consulta:\n\n"
                  f"{correccion.answer}\n\nSi no te resuelve, escalo automáticamente al equipo humano.")
    elif citas:
        answer = (
            "Soy el asistente L1 del portal. He encontrado guías que pueden resolver tu consulta:\n\n"
            + "".join(f"- {c['title']} ({c['number']})\n" for c in citas)
            + "Por favor revisa estos pasos y confirma si te funcionó. "
            "Si no, escalo automáticamente al equipo humano."
        )
    else:
        registrar_hueco(db, query, "portal_bot")
        answer = (
            "Soy el asistente L1 del portal. Gracias por los detalles. "
            "Estoy escalando este caso al equipo para revisión prioritaria. "
            "Mientras tanto, si puedes compartir capturas, error exacto y hora del incidente, acelerará la resolución."
        )

    bot_message = PortalConversationMessage(
        conversation_id=conversation.id,
        organization_id=conversation.organization_id,
        project_id=conversation.project_id,
        parent_message_id=latest_client_msg.id,
        sender_user_id=None,
        sender_client_id=None,
        message_type=PortalConversationMessageType.ai_summary,
        body=answer,
        raw_body=answer,
        moderation_notes="l1_bot_autoreply",
        is_internal_note=False,
        is_redacted=False,
        classification=PortalConversationClassification.public_client,
        grc_status=PortalConversationGRCStatus.allowed,
        delivered_at=_now(),
    )
    db.add(bot_message)

    conversation.last_message_at = _now()
    _audit(
        db,
        conversation,
        "portal_conversation.bot_reply",
        actor_client_id=current_client.id,
        target_type="message",
        target_id=bot_message.id,
        details={"kb_article_ids": [c["id"] for c in citas], "correction_id": correccion.id if correccion else None},
    )

    db.commit()
    emit_event(
        db,
        "portal_conversation.bot_reply",
        {"conversation_id": conversation.id},
        org_id=conversation.organization_id,
        resource_type="portal_conversation_message",
        resource_id=bot_message.id,
        project_id=conversation.project_id,
    )
    return _message_out(bot_message)


def review_message(conversation_id: str, message_id: str, decision: str, note: Optional[str], current_user, db: Session) -> dict:
    conversation = _get_team_conversation(conversation_id, current_user, db)
    message = db.query(PortalConversationMessage).filter(PortalConversationMessage.id == message_id, PortalConversationMessage.conversation_id == conversation.id).first()
    if not message:
        raise ValueError("Mensaje no encontrado")
    if message.grc_status != PortalConversationGRCStatus.pending_review:
        raise ValueError("El mensaje no está pendiente de revisión")
    if decision not in {"approved", "rejected"}:
        raise ValueError("Decisión no válida")
    message.moderation_notes = note or message.moderation_notes
    if decision == "approved":
        message.grc_status = PortalConversationGRCStatus.redacted if message.is_redacted else PortalConversationGRCStatus.allowed
        message.delivered_at = _now()
    else:
        message.grc_status = PortalConversationGRCStatus.blocked
    if message.approval_request_id:
        req = db.query(ApprovalRequest).filter(ApprovalRequest.id == message.approval_request_id).first()
        if req:
            req.status = "approved" if decision == "approved" else "rejected"
            req.final_decision = req.status
            req.final_note = note
            req.completed_at = _now()
    _refresh_conversation_status(conversation)
    _audit(db, conversation, "portal_conversation.message_reviewed", actor_user_id=current_user.id, target_type="message", target_id=message.id, details={"decision": decision, "note": note})
    db.commit()
    return _message_out(message)


def assign_participants(conversation_id: str, payload, current_user, db: Session) -> dict:
    conversation = _get_team_conversation(conversation_id, current_user, db)
    for user_id in payload.internal_user_ids:
        _ensure_participant(db, conversation, participant_type=PortalConversationParticipantType.internal_user, user_id=user_id, role_in_conversation=PortalConversationRole(payload.role_in_conversation), added_by_user_id=current_user.id)
        _audit(db, conversation, "portal_conversation.participant_added", actor_user_id=current_user.id, target_type="internal_user", target_id=user_id)
    for client_user_id in payload.client_user_ids:
        _ensure_participant(db, conversation, participant_type=PortalConversationParticipantType.client_user, client_user_id=client_user_id, role_in_conversation=PortalConversationRole(payload.role_in_conversation), added_by_user_id=current_user.id)
        _audit(db, conversation, "portal_conversation.participant_added", actor_user_id=current_user.id, target_type="client_user", target_id=client_user_id)
    db.commit()
    return get_team_conversation_detail(conversation_id, current_user, db)


def run_sla_escalations(current_user, db: Session) -> dict:
    query = _base_conversation_query(db).filter(
        PortalConversation.first_response_due_at != None,
        PortalConversation.first_response_at == None,
        PortalConversation.first_response_due_at < _now(),
        PortalConversation.escalated_at == None,
        PortalConversation.status.in_([PortalConversationStatus.active, PortalConversationStatus.pending_approval]),
    )
    if not getattr(current_user, "is_superadmin", False):
        query = query.filter(PortalConversation.organization_id == current_user.organization_id)
    conversations = query.all()
    escalated = []
    for conversation in conversations:
        recipients = []
        if conversation.assigned_group_id:
            recipients.extend(user.id for user in _resolve_group_members(conversation.assigned_group_id, db))
        if conversation.assigned_role_key:
            recipients.extend(user.id for user in db.query(User).filter(User.organization_id == conversation.organization_id, User.role == conversation.assigned_role_key, User.is_active == True).all())
        if not recipients:
            recipients.extend(participant.user_id for participant in conversation.participants if participant.removed_at is None and participant.user_id)
        conversation.escalated_at = _now()
        _audit(db, conversation, "portal_conversation.escalated", actor_user_id=current_user.id, details={"first_response_due_at": str(conversation.first_response_due_at)})
        _notify_users(db, recipients, f"Escalación SLA: {conversation.title}", "La conversación del portal superó el SLA de primera respuesta.", conversation.id)
        escalated.append(conversation.id)
    db.commit()
    return {"ok": True, "count": len(escalated), "conversation_ids": escalated}
