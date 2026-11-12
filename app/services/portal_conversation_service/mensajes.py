"""Mensajes: listado, envio, respuesta del bot L1 y revision.

Parte de `app.services.portal_conversation_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from datetime import timedelta
from typing import Optional
from sqlalchemy.orm import Session
from app.core.events import emit_event
from app.models.billing_reports import ApprovalRequest
from app.models.client_portal import ClientMessage, ClientUser
from app.models.portal_conversations import (
    PortalConversation,
    PortalConversationClassification,
    PortalConversationGRCStatus,
    PortalConversationMessage,
    PortalConversationMessageType,
    PortalConversationStatus,
)

from app.services.portal_conversation_service.politicas import _apply_message_policy
from app.services.portal_conversation_service._comun import (
    _audit,
    _enum_value,
    _get_client_conversation,
    _get_team_conversation,
    _is_legacy_conversation_id,
    _notify_users,
    _now,
)
from app.services.portal_conversation_service.hilos_antiguos import (
    _get_legacy_thread_for_client,
    _get_legacy_thread_for_team,
)
from app.services.portal_conversation_service.serializacion import (
    _legacy_message_out,
    _message_out,
)


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
