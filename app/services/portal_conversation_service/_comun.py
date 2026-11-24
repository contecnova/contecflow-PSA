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
    PortalConversationGRCStatus,
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
from app.core.codigos_de_error import ErrorConCodigo


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
        # 24-11-2026 (chat del portal completo): adjuntos, reacciones y el mensaje citado.
        joinedload(PortalConversation.messages).selectinload(PortalConversationMessage.attachments),
        joinedload(PortalConversation.messages).selectinload(PortalConversationMessage.reactions),
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
        raise ErrorConCodigo("proyecto_no_encontrado")
    if not getattr(current_user, "is_superadmin", False):
        if not current_user.organization_id or project.organization_id != current_user.organization_id:
            raise ErrorConCodigo("proyecto_no_encontrado")
    if not project.organization_id:
        raise ErrorConCodigo("error_interno", detail="Proyecto sin organization_id")
    return project


def _get_team_conversation(conversation_id: str, current_user, db: Session) -> PortalConversation:
    conversation = _base_conversation_query(db).filter(PortalConversation.id == conversation_id).first()
    if not conversation:
        raise ErrorConCodigo("conversacion_no_encontrada")
    if not getattr(current_user, "is_superadmin", False) and current_user.organization_id != conversation.organization_id:
        raise ErrorConCodigo("conversacion_no_encontrada")
    return conversation


def _cliente_puede_ver(conversation: PortalConversation, current_client: ClientUser) -> bool:
    """El cliente participa (él o su cliente), es de la misma empresa y ve el proyecto.

    24-11-2026 (chat del portal completo): la comprobación de empresa es
    explícita; antes dependía solo del filtro de tenant de la sesión.
    """
    if getattr(current_client, "organization_id", None) and conversation.organization_id != current_client.organization_id:
        return False
    accessible = set(current_client.get_project_ids())
    if conversation.project_id and conversation.project_id not in accessible:
        return False
    for participant in conversation.participants:
        if participant.removed_at is not None:
            continue
        if participant.client_user_id == current_client.id:
            return True
        if current_client.client_org_id and participant.client_org_id == current_client.client_org_id:
            return True
    return False


def _get_client_conversation(conversation_id: str, current_client: ClientUser, db: Session) -> PortalConversation:
    conversation = _base_conversation_query(db).filter(PortalConversation.id == conversation_id).first()
    if not conversation or not _cliente_puede_ver(conversation, current_client):
        raise ErrorConCodigo("conversacion_no_encontrada")
    return conversation


def _conversacion_ligera(db: Session, conversation_id: str) -> Optional[PortalConversation]:
    """La conversación con sus participantes, sin mensajes (avisos en vivo, llamadas, adjuntos)."""
    from sqlalchemy.orm import selectinload
    return db.query(PortalConversation).options(
        selectinload(PortalConversation.participants),
        joinedload(PortalConversation.policy),
    ).filter(PortalConversation.id == conversation_id).first()


def _conversacion_del_equipo(db: Session, conversation_id: str, current_user) -> PortalConversation:
    """Versión ligera de `_get_team_conversation` (misma regla de empresa)."""
    conversation = _conversacion_ligera(db, conversation_id)
    if not conversation:
        raise ErrorConCodigo("conversacion_no_encontrada")
    if not getattr(current_user, "is_superadmin", False) and current_user.organization_id != conversation.organization_id:
        raise ErrorConCodigo("conversacion_no_encontrada")
    return conversation


def _conversacion_del_cliente(db: Session, conversation_id: str, current_client: ClientUser) -> PortalConversation:
    """Versión ligera de `_get_client_conversation` (mismas reglas)."""
    conversation = _conversacion_ligera(db, conversation_id)
    if not conversation or not _cliente_puede_ver(conversation, current_client):
        raise ErrorConCodigo("conversacion_no_encontrada")
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


def _equipo_participa(db: Session, conversation: PortalConversation, current_user) -> bool:
    """Quien del equipo puede descargar adjuntos y entrar en llamadas (24-11-2026).

    Los participantes internos de la conversación (no retirados) y, para la
    revisión GRC, quien administra la empresa (`org.administrar`). Siempre de
    la misma empresa (lo comprueba antes `_get_team_conversation`).
    """
    if any(p.user_id == current_user.id and p.removed_at is None for p in conversation.participants):
        return True
    if conversation.created_by_user_id == current_user.id:
        return True
    from app.core.capacidades import tiene
    return bool(getattr(current_user, "is_superadmin", False)) or tiene(db, current_user, "org.administrar")


def visible_para_cliente(mensaje: PortalConversationMessage, client_id: Optional[str]) -> bool:
    """Lo que el cliente puede ver de un mensaje (lista, cita y adjuntos).

    24-11-2026: vive aquí (antes en `adjuntos`) para que `mensajes`, `serializacion`
    e `interaccion` no dependan de `adjuntos` y `adjuntos` pueda importar `mensajes`
    sin ciclo (tests/test_auditoria_2026_11_arquitectura_c4.py).

    24-11-2026: un mensaje del equipo pendiente de aprobación ya no se ve en el
    portal hasta que se aprueba (antes solo se ocultaban los bloqueados).
    """
    if mensaje.is_internal_note or mensaje.grc_status == PortalConversationGRCStatus.blocked:
        return False
    if mensaje.grc_status == PortalConversationGRCStatus.pending_review and mensaje.sender_client_id != client_id:
        return False
    return True
