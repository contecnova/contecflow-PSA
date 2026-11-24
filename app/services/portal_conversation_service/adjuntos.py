"""Imágenes y ficheros del chat del portal (24-11-2026, docs/portal/CHAT_DEL_PORTAL.md).

Reutiliza lo del chat interno en vez de duplicarlo:

- lectura acotada y validación de contenido de `app/core/uploads.py` (extensión,
  MIME declarado, bytes mágicos, ejecutables, comprimidos y su coherencia);
- antivirus y DLP de `collaboration.files.escanear` (cuarentena si cualquiera lo
  rechaza: el adjunto existe, se ve, y NO se descarga);
- el almacén de objetos de `collaboration._storage`, con la clave segmentada
  por empresa y conversación.

Y añade lo propio del portal, por empresa (`ajustes.leer`): adjuntos activados,
extensiones permitidas (solo acotan el catálogo) y tamaño máximo; además, que
la extensión case con lo que dicen los bytes (un PNG renombrado a `.pdf` no
entra aunque el PNG esté permitido).

La descarga va SIEMPRE por la API con la sesión: solo participantes de la
conversación, de la misma empresa (nunca enlaces firmados al portador). Se
sirve como `attachment` con el tipo que dicen los bytes y `nosniff`.

Auditoría: `portal_conversation.attachment_uploaded` / `_quarantined` /
`_downloaded` en `portal_conversation_audits`. El borrado va con el mensaje
(`interaccion.borrar_mensaje`).
"""
from __future__ import annotations

import os
from typing import Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.core.timeutil import utcnow
from app.models.portal_conversations import (
    PortalConversationAttachment,
    PortalConversationGRCStatus,
    PortalConversationMessage,
    PortalConversationStatus,
)
from app.services.portal_conversation_service import ajustes as _ajustes
from app.services.portal_conversation_service._comun import (
    _audit,
    _cliente_puede_ver,
    _equipo_participa,
    _get_client_conversation,
    _get_team_conversation,
    _is_legacy_conversation_id,
    visible_para_cliente,
)
from app.services.portal_conversation_service.mensajes import _despues_de_enviar, _validar_padre
from app.services.portal_conversation_service.politicas import _apply_message_policy
from app.services.portal_conversation_service.serializacion import _message_out

#: Qué tipos reales (bytes mágicos) puede tener cada extensión. Si los bytes
#: dicen otra cosa, se rechaza. Las que no tienen firma reconocible (texto,
#: Office antiguo) no se detectan y pasan por las demás comprobaciones.
MIME_POR_EXTENSION: dict[str, set[str]] = {
    ".pdf": {"application/pdf"},
    ".png": {"image/png"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".gif": {"image/gif"},
    ".webp": {"image/webp"},
    ".tif": {"image/tiff"},
    ".tiff": {"image/tiff"},
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    ".pptx": {"application/vnd.openxmlformats-officedocument.presentationml.presentation"},
    # La detección de ODF mira `content.xml` y no distingue texto de hoja.
    ".odt": {"application/vnd.oasis.opendocument.text"},
    ".ods": {"application/vnd.oasis.opendocument.text", "application/vnd.oasis.opendocument.spreadsheet"},
    ".doc": {"application/msword"},
    ".xls": {"application/vnd.ms-excel"},
    ".ppt": {"application/vnd.ms-powerpoint"},
    ".txt": {"text/plain"},
    ".csv": {"text/csv", "text/plain"},
    ".md": {"text/markdown", "text/plain"},
    ".json": {"application/json"},
    ".xml": {"application/xml", "text/xml"},
    ".mp4": {"video/mp4"},
    ".webm": {"video/webm", "audio/webm"},
    ".mp3": {"audio/mpeg"},
    ".m4a": {"audio/mp4"},
}

TIPO_POR_DEFECTO = "application/octet-stream"


def _extension(nombre: str) -> str:
    return os.path.splitext(nombre or "")[1].lower()


def validar_fichero(nombre: str, declarado: str, datos: bytes, ajustes: "_ajustes.AjustesDelChat") -> str:
    """Valida el contenido con las reglas de la plataforma y las de la empresa.

    Devuelve el tipo MIME con el que se guarda y se sirve (el que dicen los
    bytes; si no hay firma, el de la extensión). Lanza `ErrorDeDominio` (415)
    con el código de `uploads` o los propios del portal.
    """
    from app.core.uploads import UploadProfile, detect_mime_from_magic, validate_upload

    ext = _extension(nombre)
    if not ext or ext not in ajustes.extensiones:
        raise error(415, "portal_adjunto_tipo_no_permitido", extension=ext or "-",
                             aceptados=", ".join(ajustes.extensiones))
    # Plataforma: extensión del catálogo, MIME declarado, ejecutables,
    # comprimidos y coherencia declarado/real. Lanza ErrorDeDominio (415).
    validate_upload(nombre, declarado or "", datos, UploadProfile.ATTACHMENT)
    detectado = detect_mime_from_magic(datos)
    validos = MIME_POR_EXTENSION.get(ext, set())
    if detectado and detectado not in validos:
        raise error(415, "portal_adjunto_contenido_no_coincide", extension=ext, real=detectado)
    if detectado:
        return detectado
    return sorted(validos)[0] if validos else TIPO_POR_DEFECTO


def _comprobar_que_se_puede_escribir(conversation) -> None:
    if conversation.status in (PortalConversationStatus.closed, PortalConversationStatus.archived):
        raise error(409, "conversacion_cerrada")


def _crear(db: Session, conversation, *, nombre: str, mime: str, datos: bytes,
           mensaje: PortalConversationMessage, user_id: Optional[str], client_id: Optional[str]) -> PortalConversationAttachment:
    from app.services.collaboration._storage import storage
    from app.services.collaboration.files import escanear, nombre_para_clave_de_objeto

    av_status, _av, dlp_status, _dlp, en_cuarentena = escanear(datos)
    seguro = nombre_para_clave_de_objeto(nombre)
    clave = (f"portal-chat/{conversation.organization_id}/{conversation.id}/"
             f"{utcnow().strftime('%Y%m%d%H%M%S%f')}_{seguro}")
    guardado = storage.save_bytes(clave, datos)
    adjunto = PortalConversationAttachment(
        organization_id=conversation.organization_id,
        conversation_id=conversation.id,
        message_id=mensaje.id,
        uploaded_by_user_id=user_id,
        uploaded_by_client_id=client_id,
        name=(os.path.basename((nombre or "").replace("\\", "/")) or seguro)[:255],
        mime_type=mime,
        size_bytes=guardado.size_bytes,
        storage_provider=guardado.storage_provider,
        storage_key=guardado.storage_key,
        sha256=guardado.sha256,
        av_status=av_status,
        dlp_status=dlp_status,
        is_quarantined=en_cuarentena,
    )
    db.add(adjunto)
    db.flush()
    _audit(db, conversation,
           "portal_conversation.attachment_quarantined" if en_cuarentena else "portal_conversation.attachment_uploaded",
           actor_user_id=user_id, actor_client_id=client_id, target_type="attachment", target_id=adjunto.id,
           details={"message_id": mensaje.id, "size": guardado.size_bytes, "mime": mime,
                    "sha256": guardado.sha256, "av": av_status, "dlp": dlp_status})
    return adjunto


def _leer_con_tope(fichero, ajustes) -> bytes:
    from app.core.uploads import read_upload_within_limit_sync
    return read_upload_within_limit_sync(fichero, ajustes.max_mb * 1024 * 1024)


def subir_como_equipo(db: Session, conversation_id: str, fichero, caption: Optional[str], is_internal_note: bool,
                      parent_message_id: Optional[str], current_user) -> dict:

    if _is_legacy_conversation_id(conversation_id):
        raise error(422, "portal_adjunto_no_disponible")
    conversation = _get_team_conversation(conversation_id, current_user, db)
    _comprobar_que_se_puede_escribir(conversation)
    ajustes = _ajustes.leer(db, conversation.organization_id)
    if not ajustes.adjuntos:
        raise error(403, "portal_adjuntos_desactivados")
    datos = _leer_con_tope(fichero, ajustes)
    mime = validar_fichero(fichero.filename or "", fichero.content_type or "", datos, ajustes)
    _validar_padre(db, conversation, parent_message_id, para_cliente=False)
    cuerpo = (caption or "").strip() or (fichero.filename or "")
    mensaje = _apply_message_policy(conversation, "team", cuerpo, bool(is_internal_note), current_user.id, None,
                                    parent_message_id, "attachment", db)
    _crear(db, conversation, nombre=fichero.filename or "", mime=mime, datos=datos, mensaje=mensaje,
           user_id=current_user.id, client_id=None)
    _despues_de_enviar(db, conversation, mensaje, "team", current_user=current_user)
    db.refresh(mensaje)
    return _message_out(mensaje)


def subir_como_cliente(db: Session, conversation_id: str, fichero, caption: Optional[str],
                       parent_message_id: Optional[str], current_client) -> dict:

    if _is_legacy_conversation_id(conversation_id):
        raise error(422, "portal_adjunto_no_disponible")
    conversation = _get_client_conversation(conversation_id, current_client, db)
    _comprobar_que_se_puede_escribir(conversation)
    ajustes = _ajustes.leer(db, conversation.organization_id)
    if not ajustes.adjuntos:
        raise error(403, "portal_adjuntos_desactivados")
    datos = _leer_con_tope(fichero, ajustes)
    mime = validar_fichero(fichero.filename or "", fichero.content_type or "", datos, ajustes)
    _validar_padre(db, conversation, parent_message_id, para_cliente=True, client_id=current_client.id)
    cuerpo = (caption or "").strip() or (fichero.filename or "")
    mensaje = _apply_message_policy(conversation, "client", cuerpo, False, None, current_client.id,
                                    parent_message_id, "attachment", db)
    _crear(db, conversation, nombre=fichero.filename or "", mime=mime, datos=datos, mensaje=mensaje,
           user_id=None, client_id=current_client.id)
    _despues_de_enviar(db, conversation, mensaje, "client", current_client=current_client)
    db.refresh(mensaje)
    return _message_out(mensaje, para_cliente=True, client_id=current_client.id)


# ── Descarga ──────────────────────────────────────────────────────────────────

def _adjunto(db: Session, conversation, attachment_id: str) -> PortalConversationAttachment:
    adjunto = db.query(PortalConversationAttachment).filter(
        PortalConversationAttachment.id == attachment_id,
        PortalConversationAttachment.conversation_id == conversation.id,
        PortalConversationAttachment.organization_id == conversation.organization_id,
    ).first()
    if adjunto is None or adjunto.deleted_at is not None:
        raise error(404, "portal_adjunto_no_encontrado")
    if adjunto.is_quarantined:
        raise error(409, "portal_adjunto_en_cuarentena")
    return adjunto


def _leer(db: Session, conversation, adjunto, *, user_id=None, client_id=None) -> tuple[bytes, str, str]:
    from app.services.collaboration._storage import storage
    datos = storage.read(adjunto.storage_key)
    _audit(db, conversation, "portal_conversation.attachment_downloaded", actor_user_id=user_id,
           actor_client_id=client_id, target_type="attachment", target_id=adjunto.id,
           details={"message_id": adjunto.message_id})
    db.commit()
    return datos, adjunto.mime_type or TIPO_POR_DEFECTO, adjunto.name


def descargar_como_equipo(db: Session, conversation_id: str, attachment_id: str, current_user) -> tuple[bytes, str, str]:
    from app.services.portal_conversation_service._comun import _conversacion_del_equipo
    conversation = _conversacion_del_equipo(db, conversation_id, current_user)
    if not _equipo_participa(db, conversation, current_user):
        raise error(403, "portal_adjunto_sin_acceso")
    adjunto = _adjunto(db, conversation, attachment_id)
    return _leer(db, conversation, adjunto, user_id=current_user.id)


def descargar_como_cliente(db: Session, conversation_id: str, attachment_id: str, current_client) -> tuple[bytes, str, str]:
    from app.services.portal_conversation_service._comun import _conversacion_del_cliente
    conversation = _conversacion_del_cliente(db, conversation_id, current_client)
    if not _cliente_puede_ver(conversation, current_client):
        raise error(403, "portal_adjunto_sin_acceso")
    adjunto = _adjunto(db, conversation, attachment_id)
    mensaje = db.get(PortalConversationMessage, adjunto.message_id) if adjunto.message_id else None
    if mensaje is None or not visible_para_cliente(mensaje, current_client.id):
        raise error(404, "portal_adjunto_no_encontrado")
    return _leer(db, conversation, adjunto, client_id=current_client.id)
