"""Politicas de conversacion: asignacion, clasificacion, redaccion de datos sensibles y aprobacion de mensajes.

Parte de `app.services.portal_conversation_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
import json
import re
import uuid
from typing import Optional
from sqlalchemy.orm import Session
from app.models.billing_reports import ApprovalRequest
from app.models.portal_conversations import (
    PortalConversation,
    PortalConversationAssignmentMode,
    PortalConversationClassification,
    PortalConversationGRCStatus,
    PortalConversationMessage,
    PortalConversationMessageType,
    PortalConversationParticipantType,
    PortalConversationPolicy,
    PortalConversationRole,
)
from app.models.project import Project
from app.models.user import User

from app.services.portal_conversation_service._comun import (
    _ensure_participant,
    _enum_value,
    _notify_users,
    _now,
    _resolve_group_members,
)


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
