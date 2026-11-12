"""Conversaciones de equipo y de cliente: listado, detalle, alta, participantes y escalado por SLA.

Parte de `app.services.portal_conversation_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from datetime import timedelta
from typing import Optional
from sqlalchemy import or_
from sqlalchemy.orm import Session
from app.core.events import emit_event
from app.models.client_portal import ClientUser
from app.models.clients import Client
from app.models.portal_conversations import (
    PortalConversation,
    PortalConversationParticipant,
    PortalConversationParticipantType,
    PortalConversationRole,
    PortalConversationSource,
    PortalConversationStatus,
)
from app.models.project import Project
from app.models.user import User

from app.services.portal_conversation_service.politicas import (
    _apply_assignment_policy,
    _get_or_create_policy,
)
from app.services.portal_conversation_service._comun import (
    _audit,
    _base_conversation_query,
    _ensure_participant,
    _get_client_conversation,
    _get_project_for_team,
    _get_team_conversation,
    _is_legacy_conversation_id,
    _notify_users,
    _now,
    _resolve_group_members,
)
from app.services.portal_conversation_service.serializacion import (
    _conversation_out,
    _legacy_conversation_out,
)
from app.services.portal_conversation_service.hilos_antiguos import (
    _get_legacy_thread_for_client,
    _get_legacy_thread_for_team,
    _list_legacy_threads_for_client,
    _list_legacy_threads_for_team,
)


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
