"""Attachment endpoints — upload, AV/DLP, signed download, preview."""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.models.collaboration import (
    CollaborationAttachment, CollaborationAttachmentVersion,
    CollaborationModerationCase,
)
from app.schemas.collaboration import AttachmentOut
from app.services.collaboration import audit_log
from app.services.collaboration._permissions import _org, assert_conversation_access
from app.services.collaboration._storage import (
    FileStorage, scan_dlp, scan_with_av, storage,
)

router = APIRouter()


MAX_FILE_BYTES = 500 * 1024 * 1024  # 500 MB per the SLO


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

    # Read full body — for prod swap to streaming + multipart resumable
    data = await file.read()
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(413, "Archivo demasiado grande (máx 500 MB)")

    # Run AV + DLP synchronously (in prod this becomes a background pipeline).
    av_status, av_details = scan_with_av(data)
    dlp_status, dlp_findings = scan_dlp(data.decode("utf-8", errors="ignore")[:200_000])
    is_quarantined = (av_status == "infected") or (dlp_status == "blocked")

    key = f"{org}/{conversation_id}/{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{file.filename}"
    stored = storage.save_bytes(key, data)

    att = CollaborationAttachment(
        organization_id=org,
        conversation_id=conversation_id,
        message_id=message_id,
        uploaded_by_user_id=current_user.id,
        name=file.filename,
        mime_type=file.content_type,
        size_bytes=stored.size_bytes,
        storage_provider=stored.storage_provider,
        storage_key=stored.storage_key,
        sha256=stored.sha256,
        av_status=av_status,
        av_scanned_at=datetime.utcnow(),
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

    # Generate thumbnail asynchronously
    if not is_quarantined:
        from app.services.collaboration._queue import task_queue
        from app.services.collaboration._thumbnails import generate_for_attachment
        task_queue.enqueue(generate_for_attachment, att.id)

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
    data = await file.read()
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
    att.av_scanned_at = datetime.utcnow()
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


@router.get("/attachments/{attachment_id}", response_model=AttachmentOut, summary="Datos del adjunto")
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
    return AttachmentOut(
        id=att.id, name=att.name, mime_type=att.mime_type,
        size_bytes=att.size_bytes, storage_provider=att.storage_provider,
        av_status=att.av_status, dlp_status=att.dlp_status,
        is_quarantined=att.is_quarantined,
        download_url=download_url, preview_url=preview_url,
        created_at=att.created_at,
    )


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
