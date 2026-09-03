"""Attachment endpoints — upload, AV/DLP, signed download, preview."""
from app.core.timeutil import utcnow
from typing import Optional
import re

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.uploads import UploadProfile, read_and_validate_upload
from app.db.session import get_db
from app.models.user import User
from app.models.collaboration import (
    CollaborationAttachment, CollaborationAttachmentVersion,
    CollaborationModerationCase,
)
from app.core.responses import APIResponse
from app.schemas.collaboration import AttachmentOut
from app.services.collaboration import audit_log
from app.services.collaboration._permissions import _org, assert_conversation_access
from app.services.collaboration._storage import (
    FileStorage, scan_dlp, scan_with_av, storage,
)
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


# Auditoría 2026-08 (P1-8): aquí había un MAX_FILE_BYTES propio de 500 MB, muy
# por encima de settings.MAX_FILE_SIZE_MB (100) que este módulo ignoraba, y se
# comprobaba DESPUÉS de `await file.read()` — para rechazar 499 MB había que
# metérselos antes en memoria. Ahora el tope y la validación de contenido salen
# de app/core/uploads.py, que lee por trozos y aborta al pasarse.


def _safe_filename(name: Optional[str]) -> str:
    raw = (name or "upload").replace("\\", "/")
    base = raw.split("/")[-1].strip().strip(".")
    if not base:
        return "upload"
    # Keep object keys portable and traversal-safe.
    return re.sub(r"[^A-Za-z0-9._-]", "_", base)[:180] or "upload"


@router.post("/attachments", response_model=AttachmentOut, summary="Subir adjunto (multipart)")
async def upload_attachment(
    conversation_id: str = Form(...),
    message_id: Optional[str] = Form(None),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    assert_conversation_access(db, current_user, conversation_id)
    org = _org(current_user)

    # Lectura acotada + validación de tipo (extensión, MIME declarado, bytes
    # mágicos y coherencia entre ellos). Antes esto no validaba NADA del
    # contenido: bastaba renombrar un ejecutable para subirlo.
    data = await read_and_validate_upload(file, UploadProfile.ATTACHMENT)

    # Run AV + DLP synchronously (in prod this becomes a background pipeline).
    av_status, av_details = scan_with_av(data)
    dlp_status, dlp_findings = scan_dlp(data.decode("utf-8", errors="ignore")[:200_000])
    is_quarantined = (av_status == "infected") or (dlp_status == "blocked")

    safe_name = _safe_filename(file.filename)
    key = f"{org}/{conversation_id}/{utcnow().strftime('%Y%m%d%H%M%S')}_{safe_name}"
    stored = storage.save_bytes(key, data)

    att = CollaborationAttachment(
        organization_id=org,
        conversation_id=conversation_id,
        message_id=message_id,
        uploaded_by_user_id=current_user.id,
        name=safe_name,
        mime_type=file.content_type,
        size_bytes=stored.size_bytes,
        storage_provider=stored.storage_provider,
        storage_key=stored.storage_key,
        sha256=stored.sha256,
        av_status=av_status,
        av_scanned_at=utcnow(),
        dlp_status=dlp_status,
        dlp_findings={"items": dlp_findings},
        is_quarantined=is_quarantined,
    )
    db.add(att)
    db.flush()
    # Initial version
    db.add(CollaborationAttachmentVersion(
        organization_id=org, attachment_id=att.id, version=1,
        storage_key=stored.storage_key, size_bytes=stored.size_bytes,
        sha256=stored.sha256, uploaded_by_user_id=current_user.id,
    ))
    if is_quarantined:
        db.add(CollaborationModerationCase(
            organization_id=org, attachment_id=att.id,
            reason="av" if av_status == "infected" else "dlp",
            findings={"av": av_details, "dlp": dlp_findings},
            verdict="quarantined",
        ))
    audit_log.write(
        db, organization_id=org, actor_user_id=current_user.id, actor_client_id=None,
        action="attachment.uploaded", entity_type="attachment", entity_id=att.id,
        payload={"size": stored.size_bytes, "av": av_status, "dlp": dlp_status},
    )
    db.commit()

    # Si el adjunto NO viene asociado a un mensaje existente, creamos uno
    # automáticamente para que aparezca en el chat. Si está en cuarentena,
    # creamos un mensaje system de aviso en su lugar.
    if not message_id:
        from app.models.collaboration import CollaborationMessage
        from app.services.collaboration.messages import _publish_async, _serialize_message
        from app.services.collaboration._bus import conv_channel
        body = (
            f"⚠️ Archivo bloqueado: {file.filename} ({'AV' if av_status == 'infected' else 'DLP'})"
            if is_quarantined else file.filename
        )
        new_msg = CollaborationMessage(
            organization_id=org,
            conversation_id=conversation_id,
            user_id=current_user.id,
            type="system" if is_quarantined else "file",
            status="visible",
            body=body,
            metadata_json={"attachment_id": att.id, "quarantined": is_quarantined},
            has_attachments=not is_quarantined,
            sent_at=utcnow(),
        )
        db.add(new_msg); db.flush()
        # Vincular el adjunto al mensaje recién creado ANTES de serializar
        att.message_id = new_msg.id
        # Actualizar last_activity de la conversación
        from app.models.collaboration import CollaborationConversation
        conv = db.query(CollaborationConversation).filter(CollaborationConversation.id == conversation_id).first()
        if conv:
            conv.last_activity_at = utcnow()
            conv.last_message_id = new_msg.id
        db.commit()
        # Realtime publish con los attachments ya enlazados
        _publish_async(conv_channel(conversation_id), {
            "type": "message.created",
            "conversation_id": conversation_id,
            "message_id": new_msg.id,
            "payload": _serialize_message(db, new_msg),
        })

    # Generate thumbnail asynchronously
    if not is_quarantined:
        from app.services.collaboration._queue import task_queue
        from app.services.collaboration._thumbnails import generate_for_attachment
        from app.services.collaboration._text_extract import extract_text
        task_queue.enqueue(generate_for_attachment, att.id)
        # Extract text body for search index (best-effort, sync to keep dev simple)
        try:
            text = extract_text(data, safe_name, file.content_type)
            if text:
                att.text_index = text
                db.commit()
        # intentional: best-effort fallback, log noise outweighs diagnostic value
        except Exception:
            # El `rollback()` NO es cosmetico. Si lo que fallo fue el
            # `db.commit()`, la sesion queda en transaccion abortada y la
            # construccion de la respuesta de abajo lee atributos de `att` que
            # el commit anterior expiro (`expire_on_commit` esta en su valor por
            # defecto, True): SQLAlchemy intenta refrescarlos, lanza
            # `PendingRollbackError`, y una subida CORRECTA se convierte en un
            # 500 por un indice de texto que era best-effort.
            # Auditoria 2026-08, hallazgo 22.
            db.rollback()
            logger.debug("upload_attachment: fallo best-effort ignorado", exc_info=True)

    download_url = None if is_quarantined else storage.signed_url(stored.storage_key, ttl_seconds=3600)
    return AttachmentOut(
        id=att.id, name=att.name, mime_type=att.mime_type,
        size_bytes=att.size_bytes, storage_provider=att.storage_provider,
        av_status=att.av_status, dlp_status=att.dlp_status,
        is_quarantined=att.is_quarantined,
        download_url=download_url, preview_url=None,
        created_at=att.created_at,
    )


@router.post("/attachments/{attachment_id}/versions", response_model=AttachmentOut, summary="Subir nueva versión")
async def upload_new_version(
    attachment_id: str,
    notes: Optional[str] = Form(None),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    org = _org(current_user)
    att = db.query(CollaborationAttachment).filter(CollaborationAttachment.id == attachment_id, CollaborationAttachment.organization_id == org).first()
    if not att:
        raise HTTPException(404, "Adjunto no encontrado")
    assert_conversation_access(db, current_user, att.conversation_id)
    # Esta vía (subir una versión nueva de un adjunto) no tenía ni el tope de
    # 500 MB que sí tenía la de creación: era un `await file.read()` sin límite.
    data = await read_and_validate_upload(file, UploadProfile.ATTACHMENT)
    av_status, av_details = scan_with_av(data)
    dlp_status, dlp_findings = scan_dlp(data.decode("utf-8", errors="ignore")[:200_000])
    is_quarantined = (av_status == "infected") or (dlp_status == "blocked")
    next_v = (db.query(CollaborationAttachmentVersion).filter(CollaborationAttachmentVersion.attachment_id == attachment_id).count() or 0) + 1
    key = f"{att.storage_key}.v{next_v}"
    stored = storage.save_bytes(key, data)
    db.add(CollaborationAttachmentVersion(
        organization_id=org, attachment_id=attachment_id, version=next_v,
        storage_key=stored.storage_key, size_bytes=stored.size_bytes,
        sha256=stored.sha256, uploaded_by_user_id=current_user.id, notes=notes,
    ))
    # Update head
    att.storage_key = stored.storage_key
    att.size_bytes = stored.size_bytes
    att.sha256 = stored.sha256
    att.av_status = av_status
    att.av_scanned_at = utcnow()
    att.dlp_status = dlp_status
    att.dlp_findings = {"items": dlp_findings}
    att.is_quarantined = is_quarantined
    audit_log.write(
        db, organization_id=org, actor_user_id=current_user.id, actor_client_id=None,
        action="attachment.versioned", entity_type="attachment", entity_id=att.id,
        payload={"version": next_v},
    )
    db.commit()
    download_url = None if is_quarantined else storage.signed_url(att.storage_key, ttl_seconds=3600)
    return AttachmentOut(
        id=att.id, name=att.name, mime_type=att.mime_type,
        size_bytes=att.size_bytes, storage_provider=att.storage_provider,
        av_status=att.av_status, dlp_status=att.dlp_status,
        is_quarantined=att.is_quarantined,
        download_url=download_url, preview_url=None,
        created_at=att.created_at,
    )


@router.get("/attachments/{attachment_id}", response_model=APIResponse[AttachmentOut], summary="Datos del adjunto")
def get_attachment(attachment_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    org = _org(current_user)
    att = db.query(CollaborationAttachment).filter(CollaborationAttachment.id == attachment_id, CollaborationAttachment.organization_id == org).first()
    if not att:
        raise HTTPException(404, "Adjunto no encontrado")
    assert_conversation_access(db, current_user, att.conversation_id)
    download_url = None if att.is_quarantined else storage.signed_url(att.storage_key, ttl_seconds=3600)
    preview_url = None
    if att.preview_status == "ready" and att.preview_key:
        preview_url = storage.signed_url(att.preview_key, ttl_seconds=3600)
    return APIResponse.ok(data=AttachmentOut(
        id=att.id, name=att.name, mime_type=att.mime_type,
        size_bytes=att.size_bytes, storage_provider=att.storage_provider,
        av_status=att.av_status, dlp_status=att.dlp_status,
        is_quarantined=att.is_quarantined,
        download_url=download_url, preview_url=preview_url,
        created_at=att.created_at,
    ))


@router.get("/files/by-token/{token}", summary="Descargar archivo por token firmado")
def download_by_token(token: str, db: Session = Depends(get_db)):
    rec = FileStorage.resolve_token(token)
    if not rec:
        raise HTTPException(404, "Token inválido o caducado")
    data = storage.read(rec["key"])
    # Lookup mime type best-effort from attachment metadata
    att = db.query(CollaborationAttachment).filter(CollaborationAttachment.storage_key == rec["key"]).first()
    audit_log.write(
        db, organization_id=att.organization_id if att else "00000000-0000-0000-0000-000000000000",
        actor_user_id=None, actor_client_id=None,
        action="attachment.downloaded", entity_type="attachment",
        entity_id=att.id if att else None,
        payload={"key": rec["key"]},
    )
    db.commit()
    return Response(content=data, media_type=(att.mime_type if att else "application/octet-stream"))
