"""Chat del portal sobre colaboración: lo que el cliente hace en la pestaña «Chat» (24-11-2026).

Docs: docs/portal/CHAT_DEL_PORTAL.md §9. Es la misma funcionalidad que las
conversaciones gobernadas, sobre el dominio de colaboración (las conversaciones
a las que el equipo invita al cliente desde el chat interno). Reutiliza:

- los ajustes por empresa `portal_chat` (`portal_conversation_service.ajustes`):
  adjuntos, extensiones, tamaño, plazo de edición, llamadas, vídeo y tono;
- la validación de fichero por contenido (`portal_conversation_service.adjuntos
  .validar_fichero`), el antivirus/DLP y el almacén de colaboración;
- el envío único de colaboración (`messages.send_message`), su auditoría
  (`collaboration_audit_events`), su bus en tiempo real y su retención y
  bloqueo legal (`compliance`).

**Solo el operador llama.** El cliente no tiene ninguna vía de servicio para
crear una `CollaborationCall`: `iniciar_denegado` responde SIEMPRE 403
`portal_llamada_solo_operador` (y lo audita). Solo acepta (si suena; es la
única forma de recibir su token de LiveKit), rechaza o cuelga. En el lado del
operador, iniciar en una conversación con clientes exige `clientes.llamar` y
que la empresa tenga activadas las llamadas (y el vídeo) del portal
(`exigir_llamada_permitida`, desde `calls.start_call`).

**Grabación solo con consentimiento** (24-11-2026, migración 214, §11). En una
conversación con clientes se graba, se transcribe o se activa el asistente de
reuniones solo si la empresa lo permite (si no, 409
`portal_grabacion_desactivada`) y todos los clientes de la llamada han dado su
consentimiento (si no, 409 `portal_grabacion_sin_consentimiento`):
`exigir_grabacion_consentida`, que delega en
`portal_conversation_service.grabacion`.

**Validación también para el operador.** Un adjunto que sube el equipo a una
conversación con clientes pasa por las mismas reglas de la empresa
(`validar_si_hay_clientes`, desde `files.crear_adjunto`).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import timedelta
from types import SimpleNamespace
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.core.timeutil import utcnow
from app.models.collaboration import (
    CollaborationAttachment,
    CollaborationAttachmentVersion,
    CollaborationCall,
    CollaborationCallParticipant,
    CollaborationConversation,
    CollaborationConversationMember,
    CollaborationDirectConversation,
    CollaborationMessage,
    CollaborationMessageVersion,
    CollaborationReaction,
)
from app.services.collaboration import audit_log
from app.services.collaboration._bus import bus, client_user_channel, conv_channel
from app.services.collaboration._permissions import is_client_conversation_participant
from app.services.portal_conversation_service import ajustes as _ajustes

log = logging.getLogger(__name__)

#: Tipos de mensaje que su autor puede editar o borrar.
EDITABLES = ("text", "file")
#: Vida del token de LiveKit del cliente (s).
TTL_DEL_TOKEN = 2 * 3600
#: Mensaje del WebSocket del portal con «escribiendo…».
ESCRIBIENDO = "portal_collab_typing"
#: Tipo de los avisos que se reenvían al portal.
TIPO_DE_AVISO = "portal_collab"


# ── Quién es cliente en una conversación ─────────────────────────────────────

def clientes_de(db: Session, conversation_id: str) -> set[str]:
    """Los usuarios del portal que participan en la conversación."""
    ids: set[str] = set()
    d = db.query(CollaborationDirectConversation).filter(
        CollaborationDirectConversation.conversation_id == conversation_id).first()
    if d is not None:
        ids.update(x for x in (d.client_user_a_id, d.client_user_b_id) if x)
    ids.update(r[0] for r in db.query(CollaborationConversationMember.client_user_id).filter(
        CollaborationConversationMember.conversation_id == conversation_id,
        CollaborationConversationMember.client_user_id.isnot(None)).all())
    return ids


def conversacion_con_clientes(db: Session, conversation_id: Optional[str]) -> bool:
    return bool(conversation_id) and bool(clientes_de(db, conversation_id))


def _participa(db: Session, client, conversation_id: str) -> bool:
    """Participa y es de la misma empresa (la comprobación del permiso no mira la empresa)."""
    conv = db.query(CollaborationConversation).filter(CollaborationConversation.id == conversation_id).first()
    if conv is None or conv.organization_id != getattr(client, "organization_id", None):
        return False
    return is_client_conversation_participant(db, client, conversation_id)


def _exigir_participa(db: Session, client, conversation_id: str) -> None:
    if not _participa(db, client, conversation_id):
        raise error(403, "sin_acceso_conversacion")


# ── Reglas para el operador (las llaman los servicios internos) ──────────────

def exigir_llamada_permitida(db: Session, user, conversation_id: str, kind: str) -> None:
    """`calls.start_call`: en una conversación con clientes, solo con permiso y si la empresa lo deja."""
    if not conversacion_con_clientes(db, conversation_id):
        return
    from app.core.capacidades import tiene
    aj = _ajustes.leer(db, getattr(user, "organization_id", None))
    if not aj.llamadas:
        raise error(403, "portal_llamadas_desactivadas")
    if kind == "video" and not aj.video:
        raise error(403, "portal_videollamadas_desactivadas")
    if not (getattr(user, "is_superadmin", False) or tiene(db, user, "clientes.llamar")):
        raise error(403, "portal_llamada_sin_capacidad")


def exigir_grabacion_consentida(db: Session, call_id: str, *, transcripcion: bool = False) -> Optional[str]:
    """Grabar, transcribir o activar el asistente con clientes: solo con permiso de la empresa y su consentimiento.

    Sin clientes en la conversación no aplica (`None`). Con clientes devuelve el
    id de la grabación de la ronda consentida o lanza 409
    `portal_grabacion_desactivada` / `portal_transcripcion_desactivada` /
    `portal_grabacion_sin_consentimiento`.
    """
    call = db.query(CollaborationCall).filter(CollaborationCall.id == call_id).first()
    if call is None or not conversacion_con_clientes(db, call.conversation_id):
        return None
    from app.services.portal_conversation_service import grabacion
    return grabacion.exigir_consentimiento(db, "colaboracion", call.id, call.organization_id,
                                           transcripcion=transcripcion)


def _grabando(db: Session, call) -> bool:
    from app.services.portal_conversation_service import grabacion
    return grabacion.grabando(db, "colaboracion", call.id, call.organization_id)


def validar_si_hay_clientes(db: Session, organization_id: str, conversation_id: str, nombre: str,
                            declarado: Optional[str], datos: bytes) -> Optional[str]:
    """`files.crear_adjunto`: el equipo sube a una conversación con clientes con las reglas de la empresa.

    Devuelve el tipo real con el que guardar, o `None` si no hay clientes (se
    queda la validación de siempre).
    """
    if not conversacion_con_clientes(db, conversation_id):
        return None
    from app.services.portal_conversation_service.adjuntos import validar_fichero
    aj = _ajustes.leer(db, organization_id)
    if not aj.adjuntos:
        raise error(403, "portal_adjuntos_desactivados")
    if len(datos) > aj.max_mb * 1024 * 1024:
        raise error(413, "fichero_demasiado_grande", max=aj.max_mb)
    return validar_fichero(nombre or "", declarado or "", datos, aj)


# ── Adjuntos del cliente ─────────────────────────────────────────────────────

def _validar_padre(db: Session, conversation_id: str, parent_id: Optional[str]) -> None:
    if not parent_id:
        return
    padre = db.query(CollaborationMessage).filter(
        CollaborationMessage.id == parent_id,
        CollaborationMessage.conversation_id == conversation_id,
    ).first()
    if padre is None or padre.status == "deleted":
        raise error(422, "portal_mensaje_citado_no_valido")


def subir_adjunto(db: Session, client, conversation_id: str, fichero, caption: Optional[str],
                  parent_message_id: Optional[str]) -> CollaborationMessage:
    from app.core.uploads import read_upload_within_limit_sync
    from app.services.collaboration import portal as _portal
    from app.services.collaboration._storage import storage
    from app.services.collaboration.files import _atajo_de_cuarentena, escanear, nombre_para_clave_de_objeto
    from app.services.portal_conversation_service.adjuntos import validar_fichero

    _exigir_participa(db, client, conversation_id)
    org = client.organization_id
    aj = _ajustes.leer(db, org)
    if not aj.adjuntos:
        raise error(403, "portal_adjuntos_desactivados")
    datos = read_upload_within_limit_sync(fichero, aj.max_mb * 1024 * 1024)
    nombre = os.path.basename((fichero.filename or "").replace("\\", "/")) or "archivo"
    mime = validar_fichero(nombre, fichero.content_type or "", datos, aj)
    _validar_padre(db, conversation_id, parent_message_id)

    av_status, av_details, dlp_status, dlp_findings, en_cuarentena = escanear(datos)
    clave = f"{org}/{conversation_id}/{utcnow().strftime('%Y%m%d%H%M%S%f')}_portal_{nombre_para_clave_de_objeto(nombre)}"
    guardado = storage.save_bytes(clave, datos)
    att = CollaborationAttachment(
        organization_id=org, conversation_id=conversation_id, message_id=None,
        uploaded_by_user_id=None, uploaded_by_client_id=client.id,
        name=nombre[:500], mime_type=mime, size_bytes=guardado.size_bytes,
        storage_provider=guardado.storage_provider, storage_key=guardado.storage_key, sha256=guardado.sha256,
        av_status=av_status, av_scanned_at=utcnow(), dlp_status=dlp_status, dlp_findings={"items": dlp_findings},
        is_quarantined=en_cuarentena,
    )
    db.add(att)
    db.flush()
    db.add(CollaborationAttachmentVersion(
        organization_id=org, attachment_id=att.id, version=1, storage_key=guardado.storage_key,
        size_bytes=guardado.size_bytes, sha256=guardado.sha256, uploaded_by_user_id=None,
    ))
    if en_cuarentena:
        _atajo_de_cuarentena(db, org, att.id, av_status=av_status, av_details=av_details, dlp_findings=dlp_findings)
    audit_log.write(
        db, organization_id=org, actor_user_id=None, actor_client_id=client.id,
        action="attachment.quarantined" if en_cuarentena else "attachment.uploaded",
        entity_type="attachment", entity_id=att.id,
        payload={"conversation_id": conversation_id, "size": guardado.size_bytes, "mime": mime,
                 "sha256": guardado.sha256, "av": av_status, "dlp": dlp_status, "kind": "client"},
    )
    db.flush()
    cuerpo = (caption or "").strip() or nombre
    msg = _portal.send_message(db, client, SimpleNamespace(
        conversation_id=conversation_id, body=cuerpo, parent_message_id=parent_message_id,
        type="system" if en_cuarentena else "file",
        metadata_json={"attachment_id": att.id, "quarantined": en_cuarentena},
    ))
    att.message_id = msg.id
    msg.has_attachments = not en_cuarentena
    db.commit()
    _publicar(msg.conversation_id, "message.updated", msg.id)
    return msg


def descargar_adjunto(db: Session, client, attachment_id: str) -> tuple[bytes, str, str]:
    from app.services.collaboration._storage import storage
    att = db.query(CollaborationAttachment).filter(
        CollaborationAttachment.id == attachment_id,
        CollaborationAttachment.organization_id == client.organization_id,
    ).first()
    if att is None or not _participa(db, client, att.conversation_id):
        raise error(404, "portal_adjunto_no_encontrado")
    if att.is_quarantined:
        raise error(409, "portal_adjunto_en_cuarentena")
    if att.message_id:
        msg = db.query(CollaborationMessage).filter(CollaborationMessage.id == att.message_id).first()
        if msg is None or msg.status == "deleted":
            raise error(404, "portal_adjunto_no_encontrado")
    datos = storage.read(att.storage_key)
    audit_log.write(
        db, organization_id=att.organization_id, actor_user_id=None, actor_client_id=client.id,
        action="attachment.downloaded", entity_type="attachment", entity_id=att.id,
        payload={"conversation_id": att.conversation_id, "kind": "client"},
    )
    db.commit()
    return datos, att.mime_type or "application/octet-stream", att.name


# ── Editar, borrar, reaccionar ───────────────────────────────────────────────

def _mensaje_propio(db: Session, client, message_id: str) -> CollaborationMessage:
    msg = db.query(CollaborationMessage).filter(
        CollaborationMessage.id == message_id,
        CollaborationMessage.organization_id == client.organization_id,
    ).first()
    if msg is None or not _participa(db, client, msg.conversation_id):
        raise error(404, "mensaje_no_encontrado")
    if msg.client_user_id != client.id:
        raise error(403, "portal_mensaje_no_propio")
    if msg.status == "deleted":
        raise error(409, "portal_mensaje_ya_borrado")
    if getattr(msg.type, "value", msg.type) not in EDITABLES:
        raise error(422, "portal_mensaje_no_editable")
    minutos = _ajustes.leer(db, client.organization_id).minutos_de_edicion
    if minutos and msg.sent_at is not None:
        # SQLite devuelve fechas sin zona: se comparan las dos sin zona (ambas en UTC).
        enviado, ahora = msg.sent_at.replace(tzinfo=None), utcnow().replace(tzinfo=None)
        if ahora - enviado > timedelta(minutes=minutos):
            raise error(409, "portal_mensaje_fuera_de_plazo", minutos=minutos)
    return msg


def _version(db: Session, msg: CollaborationMessage, tipo: str, *, client_id=None, user_id=None) -> None:
    db.add(CollaborationMessageVersion(
        organization_id=msg.organization_id, message_id=msg.id, body=msg.body, body_html=msg.body_html,
        metadata_json=msg.metadata_json or {}, edited_by_user_id=user_id, edited_by_client_id=client_id,
        change_type=tipo,
    ))


def editar(db: Session, client, message_id: str, body: str) -> CollaborationMessage:
    from app.services.collaboration._search import search_engine
    from app.services.collaboration._storage import scan_dlp
    texto = (body or "").strip()
    if not texto:
        raise error(422, "mensaje_vacio")
    msg = _mensaje_propio(db, client, message_id)
    if texto == msg.body:
        return msg
    _version(db, msg, "edit", client_id=client.id)
    dlp_status, _ = scan_dlp(texto)
    msg.is_redacted = dlp_status == "blocked"
    msg.body = "[REDACTED — DLP]" if msg.is_redacted else texto
    msg.edited_at = utcnow()
    msg.status = "edited"
    audit_log.write(
        db, organization_id=msg.organization_id, actor_user_id=None, actor_client_id=client.id,
        action="message.edited", entity_type="message", entity_id=msg.id,
        payload={"conversation_id": msg.conversation_id, "dlp": dlp_status, "kind": "client"},
    )
    db.commit()
    try:
        search_engine.index(db, msg.id)
    except Exception:
        log.debug("chat del portal: indexado best-effort", exc_info=True)
    _publicar(msg.conversation_id, "message.updated", msg.id)
    return msg


def borrar(db: Session, client, message_id: str) -> CollaborationMessage:
    from app.services.collaboration._search import search_engine
    from app.services.collaboration.compliance import _purgar_adjuntos, legal_held_message_ids
    msg = _mensaje_propio(db, client, message_id)
    if msg.id in legal_held_message_ids(db, msg.organization_id):
        raise error(409, "portal_mensaje_bajo_bloqueo_legal", caso="collaboration")
    _version(db, msg, "delete", client_id=client.id)
    adjuntos = [a.id for a in db.query(CollaborationAttachment).filter(
        CollaborationAttachment.message_id == msg.id).all()]
    _purgar_adjuntos(db, msg.organization_id, [msg.id])
    db.query(CollaborationReaction).filter(CollaborationReaction.message_id == msg.id).delete(synchronize_session=False)
    msg.status = "deleted"
    msg.deleted_at = utcnow()
    msg.body = "[mensaje eliminado]"
    msg.has_attachments = False
    for att_id in adjuntos:
        audit_log.write(
            db, organization_id=msg.organization_id, actor_user_id=None, actor_client_id=client.id,
            action="attachment.deleted", entity_type="attachment", entity_id=att_id,
            payload={"message_id": msg.id, "kind": "client"},
        )
    audit_log.write(
        db, organization_id=msg.organization_id, actor_user_id=None, actor_client_id=client.id,
        action="message.deleted", entity_type="message", entity_id=msg.id,
        payload={"conversation_id": msg.conversation_id, "attachments": adjuntos, "kind": "client"},
    )
    db.commit()
    try:
        search_engine.remove(db, msg.id)
    except Exception:
        log.debug("chat del portal: quitar del índice best-effort", exc_info=True)
    _publicar(msg.conversation_id, "message.deleted", msg.id)
    return msg


def reaccionar(db: Session, client, message_id: str, emoji: str) -> dict:
    from app.services.portal_conversation_service.interaccion import MAX_LONGITUD_DE_REACCION, _REACCION_NO_VALIDA
    emoji = (emoji or "").strip()
    if not emoji or len(emoji) > MAX_LONGITUD_DE_REACCION or _REACCION_NO_VALIDA.search(emoji):
        raise error(422, "portal_reaccion_no_valida")
    msg = db.query(CollaborationMessage).filter(
        CollaborationMessage.id == message_id,
        CollaborationMessage.organization_id == client.organization_id,
    ).first()
    if msg is None or not _participa(db, client, msg.conversation_id):
        raise error(404, "mensaje_no_encontrado")
    if msg.status == "deleted":
        raise error(409, "portal_mensaje_ya_borrado")
    existente = db.query(CollaborationReaction).filter(
        CollaborationReaction.message_id == message_id,
        CollaborationReaction.client_user_id == client.id,
        CollaborationReaction.emoji == emoji,
    ).first()
    if existente:
        db.delete(existente)
    else:
        db.add(CollaborationReaction(organization_id=msg.organization_id, message_id=message_id,
                                     client_user_id=client.id, emoji=emoji))
    accion = "reaction.removed" if existente else "reaction.added"
    audit_log.write(
        db, organization_id=msg.organization_id, actor_user_id=None, actor_client_id=client.id,
        action=accion, entity_type="message", entity_id=message_id, payload={"emoji": emoji, "kind": "client"},
    )
    db.commit()
    _publicar(msg.conversation_id, accion, message_id,
              {"emoji": emoji, "client_user_id": client.id, "added": existente is None})
    return {"toggled": True, "added": existente is None}


def versiones_del_cliente(db: Session, client, message_id: str) -> list[CollaborationMessageVersion]:
    """El rastro de un mensaje propio (el equipo lo ve en el chat interno)."""
    msg = db.query(CollaborationMessage).filter(
        CollaborationMessage.id == message_id,
        CollaborationMessage.organization_id == client.organization_id,
    ).first()
    if msg is None or msg.client_user_id != client.id or not _participa(db, client, msg.conversation_id):
        raise error(404, "mensaje_no_encontrado")
    return db.query(CollaborationMessageVersion).filter(
        CollaborationMessageVersion.message_id == message_id).order_by(CollaborationMessageVersion.edited_at).all()


def leido_por_el_equipo(db: Session, conversation_ids: list[str]) -> dict[str, Optional[str]]:
    """Hasta cuándo ha leído el equipo cada conversación (indicador «Leído» del cliente)."""
    from sqlalchemy import func
    from app.models.collaboration import CollaborationRead
    if not conversation_ids:
        return {}
    filas = db.query(CollaborationRead.conversation_id, func.max(CollaborationRead.last_read_at)).filter(
        CollaborationRead.conversation_id.in_(conversation_ids),
        CollaborationRead.user_id.isnot(None),
    ).group_by(CollaborationRead.conversation_id).all()
    return {c: (m.isoformat() if m else None) for c, m in filas}


# ── Llamadas (el cliente acepta, rechaza o cuelga; nunca inicia) ─────────────

def iniciar_denegado(db: Session, client, conversation_id: Optional[str], kind: Optional[str]) -> None:
    if conversation_id and _participa(db, client, conversation_id):
        audit_log.write(
            db, organization_id=client.organization_id, actor_user_id=None, actor_client_id=client.id,
            action="call.start_denied", entity_type="call", entity_id=None,
            payload={"conversation_id": conversation_id, "kind": kind, "motivo": "solo_operador"},
        )
        db.commit()
    raise error(403, "portal_llamada_solo_operador")


def _participacion(db: Session, call_id: str, client_id: str) -> Optional[CollaborationCallParticipant]:
    return db.query(CollaborationCallParticipant).filter(
        CollaborationCallParticipant.call_id == call_id,
        CollaborationCallParticipant.client_user_id == client_id,
    ).first()


def _estado(call) -> str:
    return getattr(call.status, "value", call.status)


def sonando(db: Session, client) -> list[dict]:
    """Llamadas del equipo que suenan para el cliente: en curso, recientes y sin contestar por él."""
    from app.services.collaboration.portal import conversaciones_del_cliente
    ids = list(conversaciones_del_cliente(db, client))
    if not ids:
        return []
    tono = _ajustes.leer(db, client.organization_id).segundos_de_tono
    desde = utcnow() - timedelta(seconds=tono)
    filas = db.query(CollaborationCall).filter(
        CollaborationCall.organization_id == client.organization_id,
        CollaborationCall.conversation_id.in_(ids),
        CollaborationCall.status == "active",
        CollaborationCall.initiated_by.isnot(None),
        CollaborationCall.started_at >= desde,
    ).order_by(CollaborationCall.started_at.desc()).all()
    return [{"id": c.id, "conversation_id": c.conversation_id, "kind": getattr(c.kind, "value", c.kind),
             "status": "ringing", "created_at": c.started_at.isoformat() if c.started_at else None,
             "is_recorded": _grabando(db, c)}
            for c in filas if _participacion(db, c.id, client.id) is None]


def _llamada(db: Session, client, call_id: str) -> CollaborationCall:
    call = db.query(CollaborationCall).filter(
        CollaborationCall.id == call_id,
        CollaborationCall.organization_id == client.organization_id,
    ).first()
    if call is None or not _participa(db, client, call.conversation_id):
        raise error(404, "portal_llamada_no_encontrada")
    return call


def aceptar(db: Session, client, call_id: str) -> dict:
    from app.services.collaboration.livekit import issue_access_token, url
    call = _llamada(db, client, call_id)
    if _estado(call) != "active":
        raise error(409, "portal_llamada_terminada")
    if not call.initiated_by:
        raise error(403, "portal_llamada_solo_operador")
    fila = _participacion(db, call.id, client.id)
    if fila is not None and fila.role == "declined":
        raise error(409, "portal_llamada_terminada")
    if fila is None:
        fila = CollaborationCallParticipant(organization_id=call.organization_id, call_id=call.id,
                                            client_user_id=client.id, role="participant")
        db.add(fila)
    fila.joined_at = utcnow()
    fila.left_at = None
    audit_log.write(
        db, organization_id=call.organization_id, actor_user_id=None, actor_client_id=client.id,
        action="call.accepted", entity_type="call", entity_id=call.id,
        payload={"conversation_id": call.conversation_id, "kind": getattr(call.kind, "value", call.kind)},
    )
    db.commit()
    _publicar(call.conversation_id, "call.accepted", None, {"call_id": call.id, "client_user_id": client.id})
    kind = getattr(call.kind, "value", call.kind)
    return {
        "id": call.id, "conversation_id": call.conversation_id, "kind": kind, "status": "active",
        "role": "participant", "is_recorded": _grabando(db, call), "livekit_url": url(),
        "livekit_room": call.livekit_room,
        "livekit_token": issue_access_token(room=call.livekit_room, identity=f"client:{client.id}",
                                            name=client.full_name, is_recorder=False, ttl_seconds=TTL_DEL_TOKEN),
    }


def rechazar(db: Session, client, call_id: str) -> dict:
    call = _llamada(db, client, call_id)
    if _estado(call) != "active" or _participacion(db, call.id, client.id) is not None:
        raise error(409, "portal_llamada_terminada")
    db.add(CollaborationCallParticipant(organization_id=call.organization_id, call_id=call.id,
                                        client_user_id=client.id, role="declined", left_at=utcnow()))
    audit_log.write(
        db, organization_id=call.organization_id, actor_user_id=None, actor_client_id=client.id,
        action="call.declined", entity_type="call", entity_id=call.id,
        payload={"conversation_id": call.conversation_id},
    )
    db.commit()
    _publicar(call.conversation_id, "call.declined", None, {"call_id": call.id, "client_user_id": client.id})
    return {"id": call.id, "status": "declined"}


def colgar(db: Session, client, call_id: str) -> dict:
    call = _llamada(db, client, call_id)
    fila = _participacion(db, call.id, client.id)
    if fila is not None and fila.left_at is None:
        fila.left_at = utcnow()
        audit_log.write(
            db, organization_id=call.organization_id, actor_user_id=None, actor_client_id=client.id,
            action="call.left", entity_type="call", entity_id=call.id,
            payload={"conversation_id": call.conversation_id},
        )
        db.commit()
        _publicar(call.conversation_id, "call.left", None, {"call_id": call.id, "client_user_id": client.id})
    return {"id": call.id, "status": "left"}


# ── Tiempo real ──────────────────────────────────────────────────────────────

def _publicar(conversation_id: str, tipo: str, message_id: Optional[str], payload: Optional[dict] = None) -> None:
    from app.services.collaboration.messages import _publish_async
    try:
        _publish_async(conv_channel(conversation_id), {
            "type": tipo, "conversation_id": conversation_id, "message_id": message_id, "payload": payload or {}})
    except Exception:
        log.debug("chat del portal: publicación best-effort", exc_info=True)


async def mensaje_del_portal(en_sesion, db: Session, client, msg: dict) -> bool:
    """`{"type": "portal_collab_typing", "conversation_id"}` del WebSocket del portal."""
    if msg.get("type") != ESCRIBIENDO:
        return False
    cid = str(msg.get("conversation_id") or "")[:36]
    if not cid or not await en_sesion(_participa, db, client, cid):
        return True
    await bus.publish(conv_channel(cid), {
        "type": "typing", "conversation_id": cid,
        "payload": {"user_id": None, "client_user_id": client.id, "name": client.full_name, "active": True},
    })
    return True


def aviso_para_el_portal(evento: dict, client_id: str) -> Optional[dict]:
    """Lo que el portal recibe de un evento del bus: tipo y conversación, nunca el contenido.

    El «escribiendo» propio no vuelve; el del equipo, sin nombre (el cliente ve «el equipo»).
    """
    tipo = evento.get("type")
    if not tipo:
        return None
    datos = evento.get("payload") or {}
    if tipo == "typing" and datos.get("client_user_id") == client_id:
        return None
    return {"type": TIPO_DE_AVISO, "event": tipo, "conversation_id": evento.get("conversation_id"),
            "call_id": datos.get("call_id") if isinstance(datos, dict) else None}


async def reenviar_al_portal(websocket, client_id: str, conversation_ids: list[str]) -> None:
    """Reenvía al WebSocket del portal los avisos del bus de sus conversaciones (hasta desconectar)."""
    canales = [conv_channel(c) for c in conversation_ids] + [client_user_channel(client_id)]
    sub = await bus.subscribe(canales)
    try:
        async for evento in sub:
            aviso = aviso_para_el_portal(evento, client_id)
            if aviso is not None:
                await websocket.send_text(json.dumps(aviso, default=str))
    except asyncio.CancelledError:
        raise
    except Exception:
        log.debug("chat del portal: reenvío del bus terminado", exc_info=True)
    finally:
        try:
            await sub.close()
        except Exception:
            log.debug("chat del portal: cierre de suscripción", exc_info=True)


# ── RGPD ─────────────────────────────────────────────────────────────────────

BORRADO = "[ERASED]"


def copia_rgpd(db: Session, client_ids: list[str], org: str) -> dict:
    if not client_ids:
        return {"portal_collaboration_chat": {"messages": [], "attachments": [], "reactions": [], "edits": [], "calls": []}}
    mensajes = db.query(CollaborationMessage).filter(
        CollaborationMessage.organization_id == org, CollaborationMessage.client_user_id.in_(client_ids)).all()
    versiones = db.query(CollaborationMessageVersion).filter(
        CollaborationMessageVersion.organization_id == org,
        or_(CollaborationMessageVersion.edited_by_client_id.in_(client_ids),
            CollaborationMessageVersion.message_id.in_([m.id for m in mensajes] or [""]))).all()
    adjuntos = db.query(CollaborationAttachment).filter(
        CollaborationAttachment.organization_id == org, CollaborationAttachment.uploaded_by_client_id.in_(client_ids)).all()
    reacciones = db.query(CollaborationReaction).filter(
        CollaborationReaction.organization_id == org, CollaborationReaction.client_user_id.in_(client_ids)).all()
    llamadas = db.query(CollaborationCallParticipant).filter(
        CollaborationCallParticipant.organization_id == org,
        CollaborationCallParticipant.client_user_id.in_(client_ids)).all()
    f = lambda v: v.isoformat() if v else None  # noqa: E731
    return {"portal_collaboration_chat": {
        "messages": [{"conversation_id": m.conversation_id, "body": m.body, "type": getattr(m.type, "value", m.type),
                      "sent_at": f(m.sent_at), "edited_at": f(m.edited_at), "deleted_at": f(m.deleted_at)}
                     for m in mensajes],
        "edits": [{"message_id": v.message_id, "change_type": v.change_type, "body": v.body, "at": f(v.edited_at)}
                  for v in versiones],
        "attachments": [{"conversation_id": a.conversation_id, "name": a.name, "mime_type": a.mime_type,
                         "size_bytes": a.size_bytes, "sha256": a.sha256, "created_at": f(a.created_at)}
                        for a in adjuntos],
        "reactions": [{"message_id": r.message_id, "emoji": r.emoji, "at": f(r.created_at)} for r in reacciones],
        "calls": [{"call_id": p.call_id, "role": p.role, "joined_at": f(p.joined_at), "left_at": f(p.left_at)}
                  for p in llamadas],
    }}


def exigir_sin_bloqueo_legal_rgpd(db: Session, client_ids: list[str], org: str) -> None:
    from app.services.collaboration.compliance import legal_held_message_ids
    if not client_ids:
        return
    retenidos = legal_held_message_ids(db, org)
    if not retenidos:
        return
    suyos = {r[0] for r in db.query(CollaborationMessage.id).filter(
        CollaborationMessage.organization_id == org, CollaborationMessage.client_user_id.in_(client_ids)).all()}
    if suyos & retenidos:
        raise error(409, "bloqueo_legal_no_suprimible", casos="collaboration")


def suprimir_rgpd(db: Session, client_ids: list[str], org: str) -> dict:
    """«[ERASED]» en sus mensajes; fuera versiones, adjuntos (y ficheros) y reacciones. No hace commit."""
    from app.services.collaboration.compliance import _purgar_adjuntos
    if not client_ids:
        return {"messages": 0, "attachments": 0, "reactions": 0, "edits": 0}
    exigir_sin_bloqueo_legal_rgpd(db, client_ids, org)
    mensajes = db.query(CollaborationMessage).filter(
        CollaborationMessage.organization_id == org, CollaborationMessage.client_user_id.in_(client_ids)).all()
    ids = [m.id for m in mensajes]
    n_versiones = db.query(CollaborationMessageVersion).filter(
        CollaborationMessageVersion.organization_id == org,
        or_(CollaborationMessageVersion.message_id.in_(ids or [""]),
            CollaborationMessageVersion.edited_by_client_id.in_(client_ids))).delete(synchronize_session=False)
    for m in mensajes:
        m.body = BORRADO
        m.body_html = None
    # Sus adjuntos (los de sus mensajes, con fichero y versiones) y cualquiera
    # que subiera sin mensaje.
    adjuntos_de_mensajes = _purgar_adjuntos(db, org, ids) if ids else 0
    db.flush()
    sueltos = [a.message_id for a in db.query(CollaborationAttachment).filter(
        CollaborationAttachment.organization_id == org,
        CollaborationAttachment.uploaded_by_client_id.in_(client_ids)).all()]
    if sueltos:
        adjuntos_de_mensajes += _purgar_adjuntos(db, org, [m for m in sueltos if m] or [""])
    n_reacciones = db.query(CollaborationReaction).filter(
        CollaborationReaction.organization_id == org,
        CollaborationReaction.client_user_id.in_(client_ids)).delete(synchronize_session=False)
    db.flush()
    return {"messages": len(mensajes), "attachments": adjuntos_de_mensajes, "reactions": int(n_reacciones or 0),
            "edits": int(n_versiones or 0)}
