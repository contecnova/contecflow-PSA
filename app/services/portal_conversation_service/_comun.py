"""Ayudantes compartidos: reloj, ids de hilos antiguos, consultas base, participantes, auditoria y avisos.

Parte de `app.services.portal_conversation_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
import json
from datetime import datetime, timezone
from app.core.timeutil import utcnow
from typing import Optional
from sqlalchemy.orm import Session, joinedload
from app.models.client_portal import ClientMessage, ClientUser
from app.models.portal_conversations import (
    PortalConversation,
    PortalConversationAudit,
    PortalConversationMessage,
    PortalConversationParticipant,
    PortalConversationParticipantType,
    PortalConversationRole,
)
from app.models.project import Project
from app.models.service_desk import AgentGroup, AgentGroupMember
from app.models.user import User
from app.services.notifications import notify_user
import logging


logger = logging.getLogger("app.services.portal_conversation_service")


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
