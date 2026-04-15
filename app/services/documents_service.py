"""
Documents service — business logic extracted from documents.py endpoint.
Covers: MIME validation, upload validation, document access checks,
        serialization, and entity-filtered listing helpers.
"""
from __future__ import annotations

import logging
import mimetypes
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# ── MIME / extension config ───────────────────────────────────────────────────

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.oasis.opendocument.text",
    "application/vnd.oasis.opendocument.spreadsheet",
    "text/plain", "text/csv", "text/markdown",
    "application/json", "application/xml", "text/xml",
    "image/jpeg", "image/png", "image/gif", "image/webp", "image/svg+xml", "image/tiff",
    "video/mp4", "video/webm", "audio/mpeg", "audio/mp4", "audio/webm",
}

ALLOWED_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".odt", ".ods", ".txt", ".csv", ".md", ".json", ".xml",
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".tiff", ".tif",
    ".mp4", ".webm", ".mp3", ".m4a",
}

BLOCKED_MAGIC_BYTES = {
    b"MZ", b"\x7fELF", b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf", b"#!/", b"#!",
}

BLOCKED_ARCHIVE_EXTENSIONS = {".zip", ".gz", ".tar", ".tgz", ".7z", ".rar"}


# ── Magic-byte MIME detection ─────────────────────────────────────────────────

def detect_mime_from_magic(content: bytes) -> Optional[str]:
    if not content:
        return None
    head = content[:16]
    if head.startswith(b"%PDF-"):             return "application/pdf"
    if head.startswith(b"\x89PNG\r\n\x1a\n"): return "image/png"
    if head.startswith(b"\xff\xd8\xff"):      return "image/jpeg"
    if head.startswith(b"GIF87a") or head.startswith(b"GIF89a"): return "image/gif"
    if head.startswith(b"RIFF") and content[8:12] == b"WEBP": return "image/webp"
    if head.startswith(b"\x1aE\xdf\xa3"):     return "video/webm"
    if head.startswith(b"ID3") or head[:2] == b"\xff\xfb": return "audio/mpeg"
    if head.startswith(b"PK\x03\x04"):
        name = (content[:2048].decode("latin-1", errors="ignore")).lower()
        if "word/" in name: return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if "xl/" in name:   return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if "ppt/" in name:  return "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        if "content.xml" in name: return "application/vnd.oasis.opendocument.text"
        return "application/zip"
    return None


def validate_upload(file_name: str, content_type: str, content: bytes) -> None:
    import os as _os
    from fastapi import HTTPException
    ext = _os.path.splitext(file_name or "")[1].lower()
    if ext in BLOCKED_ARCHIVE_EXTENSIONS:
        raise HTTPException(415, "Subida de archivos comprimidos bloqueada por seguridad (riesgo de fuga de secretos y payloads ocultos).")
    if ext and ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(415, f"Tipo de archivo no permitido (extensión: {ext}). Sube un PDF, imagen, documento Office u otro formato aprobado.")
    if content_type and content_type not in ALLOWED_MIME_TYPES:
        if content_type not in ("application/octet-stream", "binary/octet-stream"):
            raise HTTPException(415, f"Tipo de contenido no permitido: {content_type}.")
    if content:
        header = content[:8]
        for magic in BLOCKED_MAGIC_BYTES:
            if header.startswith(magic):
                raise HTTPException(415, "El contenido del archivo parece ser un ejecutable o script. Subida rechazada por seguridad.")
    detected = detect_mime_from_magic(content)
    if detected == "application/zip":
        raise HTTPException(415, "Contenedor ZIP detectado. Este tipo de archivo está bloqueado por seguridad.")
    if detected and detected not in ALLOWED_MIME_TYPES:
        raise HTTPException(415, f"Tipo de archivo detectado no permitido: {detected}")
    if (detected and content_type
            and content_type not in ("application/octet-stream", "binary/octet-stream")
            and detected != content_type):
        raise HTTPException(415, f"El tipo real del archivo ({detected}) no coincide con el Content-Type enviado ({content_type}).")


# ── Document access helpers ───────────────────────────────────────────────────

def get_document_or_404(db, doc_id: str):
    from fastapi import HTTPException
    from app.models.documents import Document
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")
    return doc


def check_document_access(doc, user, required_level=None) -> None:
    from fastapi import HTTPException
    from app.models.documents import DocumentAccessLevel
    from app.models.user import UserRole
    if required_level is None:
        required_level = DocumentAccessLevel.viewer
    if user.role == UserRole.admin:
        return
    perm = None
    for p in doc.permissions:
        if p.user_id == user.id:
            perm = p
            break
    if doc.created_by == user.id:
        return
    if doc.project:
        is_member = any(m.user_id == user.id for m in doc.project.members)
        if is_member and required_level == DocumentAccessLevel.viewer:
            return
    if perm:
        perm_exp = perm.expires_at if perm.expires_at is None or perm.expires_at.tzinfo else perm.expires_at.replace(tzinfo=timezone.utc)
        if perm_exp and perm_exp < datetime.now(timezone.utc):
            raise HTTPException(403, "Your access to this document has expired")
        levels = [DocumentAccessLevel.viewer, DocumentAccessLevel.editor, DocumentAccessLevel.admin]
        if levels.index(perm.access_level) >= levels.index(required_level):
            return
    raise HTTPException(403, "Insufficient access level to this document")


# ── Serialization ─────────────────────────────────────────────────────────────

def serialize_document(db, doc, user, generate_s3_urls: bool = True):
    from app.models.user import UserRole
    from app.services.s3_service import file_storage
    from app.schemas.documents import DocumentOut, DocumentVersionOut, DocumentPermissionOut

    visible_perms = [
        p for p in doc.permissions
        if user.role == UserRole.admin or p.user_id == user.id or doc.created_by == user.id
    ]

    versions_out = []
    for v in doc.versions:
        s3_url = None
        if generate_s3_urls and v.file_key:
            if v.s3_url and v.s3_url_expires_at:
                expires = v.s3_url_expires_at if v.s3_url_expires_at.tzinfo else v.s3_url_expires_at.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) < expires:
                    s3_url = v.s3_url
                else:
                    s3_url = file_storage.generate_presigned_url(v.file_key)
                    v.s3_url = s3_url
                    v.s3_url_expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
                    db.add(v)
            else:
                s3_url = file_storage.generate_presigned_url(v.file_key)
                v.s3_url = s3_url
                v.s3_url_expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
                db.add(v)
        versions_out.append(DocumentVersionOut(
            id=v.id, version_num=v.version_num, file_name=v.file_name,
            file_size=v.file_size, file_mime_type=v.file_mime_type,
            change_note=v.change_note, uploader_id=v.created_by,
            uploader_name=v.uploader.full_name if v.uploader else "Unknown",
            created_at=v.created_at, download_url=s3_url, s3_url=s3_url,
        ))
    db.commit()
    return DocumentOut(
        id=doc.id, title=doc.title, description=doc.description,
        category=doc.category, project_id=doc.project_id, client_id=doc.client_id,
        milestone_id=doc.milestone_id, requires_approval=doc.requires_approval,
        approval_status=doc.approval_status, is_archived=doc.is_archived,
        created_by=doc.created_by,
        created_by_name=doc.creator.full_name if doc.creator else "Unknown",
        updated_by=doc.updated_by,
        updated_by_name=doc.updater.full_name if doc.updater else None,
        approved_by=doc.approved_by,
        approved_by_name=doc.approver.full_name if doc.approver else None,
        approved_at=doc.approved_at,
        created_at=doc.created_at, updated_at=doc.updated_at,
        versions=versions_out,
        permissions=[DocumentPermissionOut(
            id=p.id, user_id=p.user_id,
            user_name=p.user.full_name if p.user else "Unknown",
            access_level=p.access_level,
            granted_by_name=p.grantor.full_name if p.grantor else None,
            granted_at=p.granted_at, expires_at=p.expires_at,
        ) for p in visible_perms],
        tags=[t.tag_name for t in doc.tags],
    )


# ── Entity-list helper ────────────────────────────────────────────────────────

def build_doc_list(docs: list) -> list:
    from app.services.s3_service import file_storage
    result = []
    for doc in docs:
        latest = doc.versions[0] if doc.versions else None
        result.append({
            "id": doc.id, "title": doc.title, "category": doc.category,
            "approval_status": doc.approval_status, "is_archived": doc.is_archived,
            "created_by_name": doc.creator.full_name if doc.creator else "Unknown",
            "created_at": str(doc.created_at)[:16] if doc.created_at else None,
            "tags": [t.tag_name for t in doc.tags],
            "version_count": len(doc.versions),
            "latest_version": {
                "id": latest.id, "version_num": latest.version_num, "file_name": latest.file_name,
                "file_size": latest.file_size, "file_mime_type": latest.file_mime_type,
                "download_url": file_storage.generate_presigned_url(latest.file_key) if latest.file_key else None,
            } if latest else None,
        })
    return result


# ── AI summary extraction ─────────────────────────────────────────────────────

def extract_document_text(file_key: str, file_name: str, file_mime_type: str) -> Optional[str]:
    """Try to extract text from a locally stored file for AI summarization."""
    from app.services.s3_service import file_storage, LocalFileStorage
    if not isinstance(file_storage, LocalFileStorage):
        return None
    try:
        raw = file_storage.get_file_bytes(file_key)
        mime = file_mime_type or ""
        file_name_lower = (file_name or "").lower()
        if "text" in mime or file_name_lower.endswith((".md", ".txt", ".csv")):
            return raw.decode("utf-8", errors="ignore")[:8000]
        if "pdf" in mime:
            try:
                import io
                from pypdf import PdfReader
                reader = PdfReader(io.BytesIO(raw))
                return "\n".join(p.extract_text() or "" for p in reader.pages[:10])[:8000]
            except Exception:
                logger.warning("Failed to extract text from PDF for AI summary", exc_info=True)
    except Exception:
        logger.warning("Failed to read document file content for AI summary", exc_info=True)
    return None
