"""Editar, borrar y reaccionar en el chat del portal (24-11-2026, docs/portal/CHAT_DEL_PORTAL.md).

- **Editar** solo el propio mensaje (texto o pie de un adjunto), dentro del plazo
  de la empresa (`PORTAL_CHAT_EDIT_WINDOW_MINUTES`, 0 = sin plazo). El texto
  nuevo pasa otra vez por la política GRC: se ocultan los datos sensibles y, si
  la política exige aprobación para ese lado, vuelve a «pendiente de revisión»
  (editar no puede saltarse una aprobación).
- **Borrar** solo el propio mensaje, en el mismo plazo. Es un borrado lógico:
  el mensaje queda como «eliminado» para todos, sus adjuntos se quitan del
  almacén (al confirmar) y sus reacciones se van. Bajo bloqueo legal (del
  mensaje o de un adjunto) no se borra: 409.
- **Rastro**: cada edición o borrado guarda el texto ANTERIOR en
  `portal_conversation_message_versions` (lo ve el equipo) y deja su entrada en
  `portal_conversation_audits` (`message_edited`, `message_deleted`,
  `attachment_deleted`).
- **Reacciones** con emoji, de equipo o cliente, sobre mensajes que cada uno ve.
"""
from __future__ import annotations

import json
import re
from datetime import timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.models.portal_conversations import (
    PortalConversationGRCStatus,
    PortalConversationMessage,
    PortalConversationMessageType,
    PortalConversationMessageVersion,
    PortalConversationReaction,
)
from app.services.portal_conversation_service import ajustes as _ajustes
from app.services.portal_conversation_service import en_vivo
from app.services.portal_conversation_service._comun import (
    _audit,
    _conversacion_del_cliente,
    _conversacion_del_equipo,
    _is_legacy_conversation_id,
    _now,
)

#: Tipos de mensaje que su autor puede editar o borrar.
EDITABLES = (PortalConversationMessageType.text, PortalConversationMessageType.attachment)
#: Una reacción es un emoji corto: sin letras ni cifras ASCII, sin marcado.
_REACCION_NO_VALIDA = re.compile(r"[A-Za-z0-9<>&\"'`\s]")
MAX_LONGITUD_DE_REACCION = 16


def _sin_legado(conversation_id: str) -> None:
    if _is_legacy_conversation_id(conversation_id):
        raise error(422, "portal_mensaje_no_editable")


def _mensaje(db: Session, conversation, message_id: str) -> PortalConversationMessage:
    m = db.query(PortalConversationMessage).filter(
        PortalConversationMessage.id == message_id,
        PortalConversationMessage.conversation_id == conversation.id,
        PortalConversationMessage.organization_id == conversation.organization_id,
    ).first()
    if m is None:
        raise error(404, "mensaje_no_encontrado")
    return m


def _comprobar_autoria_y_plazo(db: Session, conversation, m: PortalConversationMessage, *,
                               user_id: Optional[str] = None, client_id: Optional[str] = None) -> None:
    propio = (user_id is not None and m.sender_user_id == user_id) or (
        client_id is not None and m.sender_client_id == client_id)
    if not propio:
        raise error(403, "portal_mensaje_no_propio")
    if m.deleted_at is not None:
        raise error(409, "portal_mensaje_ya_borrado")
    if m.message_type not in EDITABLES:
        raise error(422, "portal_mensaje_no_editable")
    minutos = _ajustes.leer(db, conversation.organization_id).minutos_de_edicion
    if minutos and m.created_at is not None:
        creado = m.created_at if m.created_at.tzinfo else m.created_at.replace(tzinfo=_now().tzinfo)
        if _now() - creado > timedelta(minutes=minutos):
            raise error(409, "portal_mensaje_fuera_de_plazo", minutos=minutos)


def _guardar_version(db: Session, m: PortalConversationMessage, tipo: str, *, user_id=None, client_id=None) -> None:
    db.add(PortalConversationMessageVersion(
        organization_id=m.organization_id, message_id=m.id, body=m.body, raw_body=m.raw_body,
        change_type=tipo, edited_by_user_id=user_id, edited_by_client_id=client_id,
    ))


def _volver_a_aplicar_politica(db: Session, conversation, m: PortalConversationMessage, texto: str, lado: str) -> None:
    from app.services.portal_conversation_service.politicas import (
        _approver_candidates, _create_message_approval_request, _get_or_create_policy, _redact_sensitive,
        _resolve_classification,
    )
    policy = conversation.policy or _get_or_create_policy(conversation.organization_id, conversation.topic_type, db)
    keywords = json.loads(policy.sensitive_keywords or "[]")
    redactado, ocultado, notas = _redact_sensitive(texto, keywords)
    m.raw_body = texto
    m.body = redactado if policy.redact_sensitive_content else texto
    m.is_redacted = ocultado
    m.classification = _resolve_classification(conversation.topic_type, m.is_internal_note, ocultado)
    requiere = policy.requires_client_message_approval if lado == "client" else policy.requires_team_message_approval
    if requiere:
        m.grc_status = PortalConversationGRCStatus.pending_review
        m.delivered_at = None
        notas = [*notas, "approval_required", "edited"]
        aprobadores = _approver_candidates(policy, conversation, db)
        solicitud = _create_message_approval_request(m, conversation, aprobadores, db)
        if solicitud:
            m.approval_request_id = solicitud
    else:
        m.grc_status = PortalConversationGRCStatus.redacted if ocultado else PortalConversationGRCStatus.allowed
    m.moderation_notes = ", ".join(notas) if notas else None


def _editar(db: Session, conversation, message_id: str, texto: str, *, user=None, cliente=None) -> PortalConversationMessage:
    texto = (texto or "").strip()
    if not texto:
        raise error(422, "mensaje_vacio")
    m = _mensaje(db, conversation, message_id)
    user_id = user.id if user is not None else None
    client_id = cliente.id if cliente is not None else None
    _comprobar_autoria_y_plazo(db, conversation, m, user_id=user_id, client_id=client_id)
    if texto == (m.raw_body or m.body):
        return m
    _guardar_version(db, m, "edit", user_id=user_id, client_id=client_id)
    _volver_a_aplicar_politica(db, conversation, m, texto, "client" if cliente is not None else "team")
    m.edited_at = _now()
    from app.services.portal_conversation_service.mensajes import _refresh_conversation_status
    _audit(db, conversation, "portal_conversation.message_edited", actor_user_id=user_id, actor_client_id=client_id,
           target_type="message", target_id=m.id,
           details={"grc_status": getattr(m.grc_status, "value", m.grc_status)})
    db.flush()
    _refresh_conversation_status(conversation)
    db.commit()
    oculto = m.is_internal_note or (user is not None and m.grc_status == PortalConversationGRCStatus.pending_review)
    en_vivo.avisar(db, conversation, "message", {"message_id": m.id, "change": "edited"},
                   incluir_clientes=not oculto, excepto_usuario=user_id, excepto_cliente=client_id)
    return m


def _borrar(db: Session, conversation, message_id: str, *, user=None, cliente=None) -> PortalConversationMessage:
    from app.db.bloqueo_legal import _bloqueo_de, bloqueos_activos

    m = _mensaje(db, conversation, message_id)
    user_id = user.id if user is not None else None
    client_id = cliente.id if cliente is not None else None
    _comprobar_autoria_y_plazo(db, conversation, m, user_id=user_id, client_id=client_id)
    adjuntos = [a for a in (m.attachments or []) if a.deleted_at is None]
    activos = bloqueos_activos(db, conversation.organization_id)
    for a in adjuntos:
        b = _bloqueo_de("portal_conversation_attachments", a, activos)
        if b is not None:
            raise error(409, "portal_mensaje_bajo_bloqueo_legal", caso=b.case_reference)
    _guardar_version(db, m, "delete", user_id=user_id, client_id=client_id)
    ahora = _now()
    m.deleted_at = ahora
    m.deleted_by_user_id = user_id
    m.deleted_by_client_id = client_id
    for r in list(m.reactions or []):
        db.delete(r)
    claves = db.info.setdefault("portal_chat_ficheros_a_borrar", [])
    for a in adjuntos:
        a.deleted_at = ahora
        claves.append(a.storage_key)
        _audit(db, conversation, "portal_conversation.attachment_deleted", actor_user_id=user_id,
               actor_client_id=client_id, target_type="attachment", target_id=a.id,
               details={"message_id": m.id, "sha256": a.sha256, "size": a.size_bytes})
    _audit(db, conversation, "portal_conversation.message_deleted", actor_user_id=user_id, actor_client_id=client_id,
           target_type="message", target_id=m.id, details={"attachments": [a.id for a in adjuntos]})
    db.commit()
    en_vivo.avisar(db, conversation, "message", {"message_id": m.id, "change": "deleted"},
                   incluir_clientes=not m.is_internal_note, excepto_usuario=user_id, excepto_cliente=client_id)
    return m


def _reaccionar(db: Session, conversation, message_id: str, emoji: str, *, user=None, cliente=None) -> dict:
    from app.services.portal_conversation_service._comun import visible_para_cliente

    emoji = (emoji or "").strip()
    if not emoji or len(emoji) > MAX_LONGITUD_DE_REACCION or _REACCION_NO_VALIDA.search(emoji):
        raise error(422, "portal_reaccion_no_valida")
    m = _mensaje(db, conversation, message_id)
    if m.deleted_at is not None:
        raise error(409, "portal_mensaje_ya_borrado")
    if cliente is not None and not visible_para_cliente(m, cliente.id):
        raise error(404, "mensaje_no_encontrado")
    q = db.query(PortalConversationReaction).filter(
        PortalConversationReaction.message_id == m.id, PortalConversationReaction.emoji == emoji)
    q = q.filter(PortalConversationReaction.user_id == user.id) if user is not None else q.filter(
        PortalConversationReaction.client_user_id == cliente.id)
    existente = q.first()
    if existente is not None:
        db.delete(existente)
    else:
        db.add(PortalConversationReaction(
            organization_id=m.organization_id, message_id=m.id, emoji=emoji,
            user_id=user.id if user is not None else None,
            client_user_id=cliente.id if cliente is not None else None,
        ))
    db.commit()
    en_vivo.avisar(db, conversation, "reaction", {"message_id": m.id},
                   incluir_clientes=not m.is_internal_note,
                   excepto_usuario=user.id if user is not None else None,
                   excepto_cliente=cliente.id if cliente is not None else None)
    return {"message_id": m.id, "emoji": emoji, "added": existente is None}


# ── API del servicio (equipo / cliente) ───────────────────────────────────────

def _salida(m, *, cliente=None) -> dict:
    from app.services.portal_conversation_service.serializacion import _message_out
    return _message_out(m, para_cliente=cliente is not None, client_id=cliente.id if cliente is not None else None)


def editar_como_equipo(db: Session, conversation_id: str, message_id: str, texto: str, current_user) -> dict:
    _sin_legado(conversation_id)
    conv = _conversacion_del_equipo(db, conversation_id, current_user)
    return _salida(_editar(db, conv, message_id, texto, user=current_user))


def editar_como_cliente(db: Session, conversation_id: str, message_id: str, texto: str, current_client) -> dict:
    _sin_legado(conversation_id)
    conv = _conversacion_del_cliente(db, conversation_id, current_client)
    return _salida(_editar(db, conv, message_id, texto, cliente=current_client), cliente=current_client)


def borrar_como_equipo(db: Session, conversation_id: str, message_id: str, current_user) -> dict:
    _sin_legado(conversation_id)
    conv = _conversacion_del_equipo(db, conversation_id, current_user)
    return _salida(_borrar(db, conv, message_id, user=current_user))


def borrar_como_cliente(db: Session, conversation_id: str, message_id: str, current_client) -> dict:
    _sin_legado(conversation_id)
    conv = _conversacion_del_cliente(db, conversation_id, current_client)
    return _salida(_borrar(db, conv, message_id, cliente=current_client), cliente=current_client)


def reaccionar_como_equipo(db: Session, conversation_id: str, message_id: str, emoji: str, current_user) -> dict:
    _sin_legado(conversation_id)
    conv = _conversacion_del_equipo(db, conversation_id, current_user)
    return _reaccionar(db, conv, message_id, emoji, user=current_user)


def reaccionar_como_cliente(db: Session, conversation_id: str, message_id: str, emoji: str, current_client) -> dict:
    _sin_legado(conversation_id)
    conv = _conversacion_del_cliente(db, conversation_id, current_client)
    return _reaccionar(db, conv, message_id, emoji, cliente=current_client)


def versiones(db: Session, conversation_id: str, message_id: str, current_user) -> list[dict]:
    """El rastro de un mensaje (solo equipo): el texto que tenía antes de cada cambio."""
    _sin_legado(conversation_id)
    conv = _conversacion_del_equipo(db, conversation_id, current_user)
    m = _mensaje(db, conv, message_id)
    filas = db.query(PortalConversationMessageVersion).filter(
        PortalConversationMessageVersion.message_id == m.id,
    ).order_by(PortalConversationMessageVersion.edited_at).all()
    return [{
        "id": v.id, "change_type": v.change_type, "body": v.body, "raw_body": v.raw_body,
        "edited_by_user_id": v.edited_by_user_id, "edited_by_client_id": v.edited_by_client_id,
        "edited_at": str(v.edited_at)[:19] if v.edited_at else None,
    } for v in filas]


__all__ = [
    "editar_como_equipo", "editar_como_cliente", "borrar_como_equipo", "borrar_como_cliente",
    "reaccionar_como_equipo", "reaccionar_como_cliente", "versiones",
]
