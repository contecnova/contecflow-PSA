"""TUS 1.0.0 resumable uploads para adjuntos del chat.

Spec: https://tus.io/protocols/resumable-upload

Endpoints:
  POST   /collaboration/tus           — crear upload (Upload-Length, Upload-Metadata)
  PATCH  /collaboration/tus/{id}      — subir chunk (Upload-Offset, Content-Type: application/offset+octet-stream)
  HEAD   /collaboration/tus/{id}      — estado actual (Upload-Offset, Upload-Length)
  DELETE /collaboration/tus/{id}      — abortar
  OPTIONS /collaboration/tus          — capabilities

Cuando se completa Upload-Length == Upload-Offset, el server pasa el archivo a
storage + crea el CollaborationAttachment + lanza AV/DLP/thumbnail.
"""
from __future__ import annotations

import base64
import logging
import os
import re
from app.core.timeutil import utcnow
from typing import Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.core.abac_enforce import enforce_abac
from app.models.collaboration import (
    CollaborationAttachment, CollaborationAttachmentVersion, CollaborationModerationCase,
)
from app.services.collaboration import audit_log
from app.services.collaboration._permissions import _org, assert_conversation_access
from app.services.collaboration._storage import scan_dlp, scan_with_av, storage

router = APIRouter()

TUS_VERSION = "1.0.0"
TUS_EXTENSIONS = "creation,termination"
TUS_MAX_SIZE = 500 * 1024 * 1024  # 500 MB

UPLOAD_DIR = os.path.join("uploads", "collaboration", ".tus")
os.makedirs(UPLOAD_DIR, exist_ok=True)


def _meta_path(uid: str) -> str:
    return os.path.join(UPLOAD_DIR, f"{uid}.meta")


def _data_path(uid: str) -> str:
    return os.path.join(UPLOAD_DIR, f"{uid}.bin")


def _read_meta(uid: str) -> Optional[dict]:
    import json
    p = _meta_path(uid)
    if not os.path.exists(p):
        return None
    try:
        with open(p) as f:
            return json.load(f)
    except Exception:
        logger.exception("Error leyendo metadata TUS para upload %s", uid)
        return None


def _write_meta(uid: str, data: dict) -> None:
    import json
    with open(_meta_path(uid), "w") as f:
        json.dump(data, f)


def _parse_metadata(header: str) -> dict:
    out = {}
    for part in (header or "").split(","):
        part = part.strip()
        if not part:
            continue
        if " " in part:
            k, v = part.split(" ", 1)
            try:
                out[k] = base64.b64decode(v).decode("utf-8")
            except Exception:
                out[k] = ""
        else:
            out[part] = ""
    return out


def _safe_filename(name: Optional[str]) -> str:
    raw = (name or "upload").replace("\\", "/")
    base = raw.split("/")[-1].strip().strip(".")
    if not base:
        return "upload"
    return re.sub(r"[^A-Za-z0-9._-]", "_", base)[:180] or "upload"


@router.options("/tus")
def tus_options() -> Response:
    return Response(
        status_code=204,
        headers={
            "Tus-Resumable": TUS_VERSION,
            "Tus-Version": TUS_VERSION,
            "Tus-Extension": TUS_EXTENSIONS,
            "Tus-Max-Size": str(TUS_MAX_SIZE),
        },
    )


@router.post("/tus")
def tus_create(
    request: Request,
    upload_length: int = Header(..., alias="Upload-Length"),
    upload_metadata: str = Header("", alias="Upload-Metadata"),
    tus_resumable: str = Header(TUS_VERSION, alias="Tus-Resumable"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if upload_length <= 0 or upload_length > TUS_MAX_SIZE:
        raise HTTPException(413, "Tamaño no permitido")
    meta = _parse_metadata(upload_metadata)
    conversation_id = meta.get("conversationId") or meta.get("conversation_id")
    if not conversation_id:
        raise HTTPException(400, "Upload-Metadata debe incluir 'conversationId'")
    assert_conversation_access(db, current_user, conversation_id)
    import uuid
    uid = str(uuid.uuid4())
    _write_meta(uid, {
        "user_id": current_user.id,
        "organization_id": _org(current_user),
        "conversation_id": conversation_id,
        "name": _safe_filename(meta.get("filename") or meta.get("name")),
        "mime_type": meta.get("filetype") or meta.get("mime_type") or None,
        "size": upload_length,
        "offset": 0,
        "created_at": utcnow().isoformat(),
    })
    open(_data_path(uid), "wb").close()
    base = str(request.base_url).rstrip("/")
    return Response(
        status_code=201,
        headers={
            "Location": f"{base}/api/v1/collaboration/tus/{uid}",
            "Tus-Resumable": TUS_VERSION,
        },
    )


@router.head("/tus/{uid}")
def tus_head(uid: str, current_user: User = Depends(get_current_user)) -> Response:
    meta = _read_meta(uid)
    if not meta or meta.get("user_id") != current_user.id:
        raise HTTPException(404, "Upload no encontrado")
    return Response(
        status_code=200,
        headers={
            "Tus-Resumable": TUS_VERSION,
            "Upload-Offset": str(meta["offset"]),
            "Upload-Length": str(meta["size"]),
            "Cache-Control": "no-store",
        },
    )


@router.patch("/tus/{uid}")
async def tus_patch(
    uid: str,
    request: Request,
    upload_offset: int = Header(..., alias="Upload-Offset"),
    content_type: str = Header(..., alias="Content-Type"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if content_type != "application/offset+octet-stream":
        raise HTTPException(415, "Content-Type inválido")
    meta = _read_meta(uid)
    if not meta or meta.get("user_id") != current_user.id:
        raise HTTPException(404, "Upload no encontrado")
    if upload_offset != meta["offset"]:
        raise HTTPException(409, "Offset no coincide")
    body = await request.body()
    if meta["offset"] + len(body) > meta["size"]:
        raise HTTPException(413, "Excede tamaño declarado")
    with open(_data_path(uid), "ab") as f:
        f.write(body)
    meta["offset"] += len(body)
    _write_meta(uid, meta)

    # Si completo, materializa el adjunto
    if meta["offset"] == meta["size"]:
        with open(_data_path(uid), "rb") as f:
            data = f.read()
        av_status, av_details = scan_with_av(data)
        dlp_status, dlp_findings = scan_dlp(data.decode("utf-8", errors="ignore")[:200_000])
        is_quarantined = (av_status == "infected") or (dlp_status == "blocked")
        key = f"{meta['organization_id']}/{meta['conversation_id']}/{utcnow().strftime('%Y%m%d%H%M%S')}_{_safe_filename(meta['name'])}"
        stored = storage.save_bytes(key, data)
        att = CollaborationAttachment(
            organization_id=meta["organization_id"],
            conversation_id=meta["conversation_id"],
            uploaded_by_user_id=current_user.id,
            name=meta["name"],
            mime_type=meta.get("mime_type"),
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
        db.add(att); db.flush()
        db.add(CollaborationAttachmentVersion(
            organization_id=meta["organization_id"], attachment_id=att.id, version=1,
            storage_key=stored.storage_key, size_bytes=stored.size_bytes,
            sha256=stored.sha256, uploaded_by_user_id=current_user.id,
        ))
        if is_quarantined:
            db.add(CollaborationModerationCase(
                organization_id=meta["organization_id"], attachment_id=att.id,
                reason="av" if av_status == "infected" else "dlp",
                findings={"av": av_details, "dlp": dlp_findings},
                verdict="quarantined",
            ))
        audit_log.write(
            db, organization_id=meta["organization_id"],
            actor_user_id=current_user.id, actor_client_id=None,
            action="attachment.uploaded.tus", entity_type="attachment", entity_id=att.id,
            payload={"size": stored.size_bytes, "av": av_status, "dlp": dlp_status},
        )
        db.commit()

        # Thumbnail async + cleanup tus tmp
        if not is_quarantined:
            from app.services.collaboration._queue import task_queue
            from app.services.collaboration._thumbnails import generate_for_attachment
            task_queue.enqueue(generate_for_attachment, att.id)
        try:
            os.remove(_data_path(uid))
            os.remove(_meta_path(uid))
        except Exception:
            logger.exception("Error limpiando archivos temporales TUS para upload %s", uid)

    return Response(
        status_code=204,
        headers={
            "Tus-Resumable": TUS_VERSION,
            "Upload-Offset": str(meta["offset"]),
        },
    )


@router.delete("/tus/{uid}")
def tus_delete(uid: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> Response:
    enforce_abac(db, current_user, "collaboration_file", uid, action="delete")
    meta = _read_meta(uid)
    if meta and meta.get("user_id") == current_user.id:
        for p in (_data_path(uid), _meta_path(uid)):
            try:
                os.remove(p)
            except Exception:
                logger.exception("Error eliminando archivo TUS %s", p)
    return Response(status_code=204, headers={"Tus-Resumable": TUS_VERSION})
