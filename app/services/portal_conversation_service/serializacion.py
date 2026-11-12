"""Como se presentan conversaciones, participantes y mensajes (tambien los hilos antiguos).

Parte de `app.services.portal_conversation_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from app.models.client_portal import ClientMessage
from app.models.portal_conversations import (
    PortalConversation,
    PortalConversationGRCStatus,
    PortalConversationMessage,
    PortalConversationParticipant,
)

from app.services.portal_conversation_service._comun import (
    _enum_value,
    _is_past,
    _legacy_conversation_id,
)
from app.services.portal_conversation_service.politicas import _policy_out


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
