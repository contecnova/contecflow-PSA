from __future__ import annotations
from sqlalchemy.orm import Session
# Devuelve un query filtrable y el total para paginación
def query_documents(db: Session, current_user, category=None, tags=None, search=None, project_id=None, is_archived=False, task_id=None, ticket_id=None):
    q = db.query(Document).filter(Document.is_archived == is_archived)
    if category:
        q = q.filter(Document.category == category)
    if project_id:
        q = q.filter(Document.project_id == project_id)
    if task_id:
        q = q.filter(Document.task_id == task_id)
    if ticket_id:
        q = q.filter(Document.ticket_id == ticket_id)
    if search:
        q = q.filter(or_(Document.title.ilike(f"%{search}%"), Document.description.ilike(f"%{search}%")))
    if current_user.role != UserRole.admin:
        q = q.filter(or_(Document.created_by == current_user.id, Document.permissions.any(DocumentPermission.user_id == current_user.id)))
    if not current_user.is_superadmin and current_user.organization_id:
        org_user_ids = db.query(User.id).filter(User.organization_id == current_user.organization_id).scalar_subquery()
        q = q.filter(or_(Document.created_by.in_(org_user_ids), Document.permissions.any(DocumentPermission.user_id.in_(org_user_ids))))
    total = q.count()
    return q.order_by(Document.created_at.desc()), total

# Serializador compacto para listados
def serialize_doc_list_item(doc):
    latest = doc.versions[0] if doc.versions else None
    return {
        "id": doc.id,
        "title": doc.title,
        "category": doc.category,
        "requires_approval": doc.requires_approval,
        "approval_status": doc.approval_status,
        "is_archived": doc.is_archived,
        "created_by_name": doc.creator.full_name if doc.creator else "Unknown",
        "created_at": str(doc.created_at)[:16] if doc.created_at else None,
        "tags": [t.tag_name for t in doc.tags],
        "version_count": len(doc.versions),
        "latest_version": {
            "id": latest.id,
            "version_num": latest.version_num,
            "file_name": latest.file_name,
            "file_size": latest.file_size,
            "file_mime_type": latest.file_mime_type,
            "download_url": file_storage.generate_presigned_url(latest.file_key) if latest.file_key else None,
            "uploader_id": latest.created_by,
            "uploader_name": latest.uploader.full_name if latest.uploader else "Unknown",
            "created_at": latest.created_at,
        } if latest else None,
    }

"""
Documents service — business logic extracted from documents.py endpoint.
Covers: MIME validation, upload validation, document access checks,
        serialization, and entity-filtered listing helpers.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from app.core.security import decode_token
from app.models.documents import Document
from app.models.documents import DocumentAccessLevel
from app.models.documents import DocumentPermission
from app.models.documents import DocumentAccessLog
from app.models.documents import DocumentVersion
from app.models.documents import ApprovalStatus
from app.models.documents import DocumentTag, DocumentCategory
from app.models.user import UserRole
from app.models.user import User
from app.schemas.documents import DocumentOut, DocumentVersionOut, DocumentPermissionOut
from app.services.s3_service import file_storage
from app.services.s3_service import LocalFileStorage
from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy import and_

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
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")
    return doc


def check_document_access(doc, user, required_level=None) -> None:
    if required_level is None:
        required_level = DocumentAccessLevel.viewer
    if user.role == UserRole.admin:
        return
    if doc.created_by == user.id:
        return
    if doc.project:
        is_member = any(m.user_id == user.id for m in doc.project.members)
        if is_member and required_level == DocumentAccessLevel.viewer:
            return

    levels = [DocumentAccessLevel.viewer, DocumentAccessLevel.editor, DocumentAccessLevel.admin]
    user_role_value = user.role.value if hasattr(user.role, 'value') else str(user.role)
    user_dept = (user.department or '').strip().lower() if getattr(user, 'department', None) else ''
    now = datetime.now(timezone.utc)

    # Pick the strongest matching grant (user > role > department) for this user.
    best_level_idx = -1
    for p in doc.permissions:
        # Subject match: exactly one of user_id / role / department applies.
        if p.user_id and p.user_id != user.id:
            continue
        if p.role and p.role != user_role_value:
            continue
        if p.department and p.department.strip().lower() != user_dept:
            continue
        if not (p.user_id or p.role or p.department):
            continue  # malformed grant
        # Expiration
        perm_exp = p.expires_at if p.expires_at is None or p.expires_at.tzinfo else p.expires_at.replace(tzinfo=timezone.utc)
        if perm_exp and perm_exp < now:
            continue
        idx = levels.index(p.access_level)
        if idx > best_level_idx:
            best_level_idx = idx

    if best_level_idx >= levels.index(required_level):
        return
    raise HTTPException(403, "Insufficient access level to this document")


# ── Serialization ─────────────────────────────────────────────────────────────

def serialize_document(db, doc, user, generate_s3_urls: bool = True):

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
        ai_summary=doc.ai_summary,
        versions=versions_out,
        permissions=[DocumentPermissionOut(
            id=p.id, user_id=p.user_id,
            user_name=(p.user.full_name if p.user else None),
            role=p.role,
            department=p.department,
            access_level=p.access_level,
            granted_by_name=p.grantor.full_name if p.grantor else None,
            granted_at=p.granted_at, expires_at=p.expires_at,
        ) for p in visible_perms],
        tags=[t.tag_name for t in doc.tags],
        approval_request=_serialize_approval_request(db, doc),
    )


def _serialize_approval_request(db, doc) -> Optional[dict]:
    """Serialize current approval workflow state for a document."""
    if not getattr(doc, 'approval_request_id', None):
        return None
    try:
        from app.models.billing_reports import ApprovalRequest, ApprovalDecision as ADec, ApprovalStep
        ar = db.query(ApprovalRequest).filter(ApprovalRequest.id == doc.approval_request_id).first()
        if not ar:
            return None
        wf = ar.workflow
        steps = sorted(wf.steps, key=lambda s: s.step_order) if wf else []
        current_step_obj = next((s for s in steps if s.step_order == ar.current_step), None)
        decisions = db.query(ADec).filter(ADec.request_id == ar.id).order_by(ADec.decided_at).all()
        return {
            "id": ar.id,
            "status": ar.status,
            "workflow_name": wf.name if wf else None,
            "total_steps": len(steps),
            "current_step": ar.current_step,
            "current_step_name": current_step_obj.name if current_step_obj else None,
            "current_approver_type": current_step_obj.approver_type if current_step_obj else None,
            "current_approver_role": current_step_obj.approver_role if current_step_obj else None,
            "current_approver_user_id": current_step_obj.approver_user_id if current_step_obj else None,
            "current_approver_name": (
                current_step_obj.approver.full_name
                if current_step_obj and current_step_obj.approver else None
            ),
            "requested_at": ar.created_at.isoformat() if ar.created_at else None,
            "completed_at": ar.completed_at.isoformat() if ar.completed_at else None,
            "decisions": [
                {
                    "step_order": d.step_order,
                    "approver_id": d.approver_id,
                    "approver_name": d.approver.full_name if d.approver else None,
                    "decision": d.decision,
                    "note": d.note,
                    "decided_at": d.decided_at.isoformat() if d.decided_at else None,
                }
                for d in decisions
            ],
        }
    except Exception:
        logger.warning("Failed to serialize approval_request for doc %s", doc.id, exc_info=True)
        return None


# ── Entity-list helper ────────────────────────────────────────────────────────

def build_doc_list(docs: list) -> list:
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


# ── Approval-engine helpers ─────────────────────────────────────────────────

def _auto_create_approval_request(db, doc, current_user):
    """Find the best workflow for this document and open an ApprovalRequest.

    Returns the created ApprovalRequest id, or None if no workflow is configured.
    """
    from app.services.approval_engine import find_document_workflow
    from app.models.billing_reports import ApprovalRequest as ARModel
    import uuid as _uuid

    category = doc.category.value if hasattr(doc.category, 'value') else str(doc.category)
    wf = find_document_workflow(db, category)
    if not wf:
        return None

    steps = sorted(wf.steps or [], key=lambda s: s.step_order)
    if not steps:
        return None

    ar = ARModel(
        id=str(_uuid.uuid4()),
        workflow_id=wf.id,
        entity_type="document",
        entity_id=doc.id,
        entity_summary=doc.title,
        requested_by=current_user.id,
        status="pending",
        current_step=steps[0].step_order,
        step_started_at=datetime.now(timezone.utc),
    )
    db.add(ar)
    db.flush()
    doc.approval_request_id = ar.id
    db.add(doc)
    db.flush()

    # Notify first approver
    try:
        from app.services.approval_engine import notify_approver
        notify_approver(ar, steps[0], db)
    except Exception:
        logger.warning("Could not notify first approver for document %s", doc.id, exc_info=True)

    return ar.id


# ── CRUD service functions ────────────────────────────────────────────────────

def create_document(db, payload, current_user):
    doc = Document(
        title=payload.title,
        description=payload.description,
        category=payload.category,
        project_id=payload.project_id,
        client_id=payload.client_id,
        milestone_id=payload.milestone_id,
        requires_approval=payload.requires_approval,
        created_by=current_user.id,
    )
    db.add(doc)
    db.flush()
    if doc.requires_approval:
        _auto_create_approval_request(db, doc, current_user)
    db.commit()
    db.refresh(doc)
    return serialize_document(db, doc, current_user)


def list_documents(db, current_user, skip: int, limit: int, category, tags, search, project_id, is_archived: bool):
    q = db.query(Document).filter(Document.is_archived == is_archived)
    if category:
        q = q.filter(Document.category == category)
    if project_id:
        q = q.filter(Document.project_id == project_id)
    if search:
        q = q.filter(or_(
            Document.title.ilike(f"%{search}%"),
            Document.description.ilike(f"%{search}%"),
        ))
    if current_user.role != UserRole.admin:
        q = q.filter(or_(
            Document.created_by == current_user.id,
            Document.permissions.any(DocumentPermission.user_id == current_user.id),
        ))
    if not current_user.is_superadmin and current_user.organization_id:
        org_user_ids = db.query(User.id).filter(
            User.organization_id == current_user.organization_id
        ).scalar_subquery()
        q = q.filter(or_(
            Document.created_by.in_(org_user_ids),
            Document.permissions.any(DocumentPermission.user_id.in_(org_user_ids)),
        ))
    return q.order_by(Document.created_at.desc()).offset(skip).limit(limit).all()


def log_document_view(db, doc_id: str, user_id: str, ip_address):
    db.add(DocumentAccessLog(document_id=doc_id, user_id=user_id, action="view", ip_address=ip_address))
    db.commit()


def update_document(db, doc, payload, current_user):
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(doc, field, value)
    doc.updated_by = current_user.id
    db.commit()
    db.refresh(doc)
    return serialize_document(db, doc, current_user)


def archive_document(db, doc):
    doc.is_archived = True
    db.commit()


def create_document_version(db, doc, doc_id: str, file: object, content: bytes, change_note, current_user, s3_key: str, file_size: int):
    version_num = max([v.version_num for v in doc.versions], default=0) + 1
    version = DocumentVersion(
        document_id=doc_id,
        version_num=version_num,
        file_key=s3_key,
        file_name=file.filename,
        file_size=file_size,
        file_mime_type=file.content_type,
        change_note=change_note,
        created_by=current_user.id,
    )
    db.add(version)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(version)
    return version


def add_document_permission(db, doc_id: str, payload, current_user):
    """Grant access to a document. payload must specify exactly ONE of
    user_id / role / department."""
    subjects = [bool(payload.user_id), bool(payload.role), bool(payload.department)]
    if sum(subjects) != 1:
        raise HTTPException(
            status_code=400,
            detail="Provide exactly one of user_id, role or department",
        )

    user = None
    if payload.user_id:
        user = db.query(User).filter(User.id == payload.user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

    if payload.role:
        valid_roles = {r.value for r in UserRole}
        if payload.role not in valid_roles:
            raise HTTPException(status_code=400, detail=f"Invalid role: {payload.role}")

    # Detect duplicate grant (same subject)
    q = db.query(DocumentPermission).filter(DocumentPermission.document_id == doc_id)
    if payload.user_id:
        q = q.filter(DocumentPermission.user_id == payload.user_id)
    elif payload.role:
        q = q.filter(DocumentPermission.role == payload.role)
    elif payload.department:
        q = q.filter(DocumentPermission.department == payload.department)
    if q.first():
        raise HTTPException(status_code=409, detail="A grant already exists for this subject")

    perm = DocumentPermission(
        document_id=doc_id,
        user_id=payload.user_id,
        role=payload.role,
        department=payload.department,
        access_level=payload.access_level,
        granted_by=current_user.id,
        expires_at=payload.expires_at,
    )
    db.add(perm)
    db.commit()
    db.refresh(perm)
    return perm, user


def list_document_permissions(db, doc_id: str):
    """Return all permission rows for a document, with subject names hydrated."""
    perms = db.query(DocumentPermission).filter(DocumentPermission.document_id == doc_id).all()
    out = []
    for p in perms:
        user_name = None
        granted_by_name = None
        if p.user_id and p.user:
            user_name = p.user.full_name
        if p.granted_by and p.grantor:
            granted_by_name = p.grantor.full_name
        out.append({
            "id": p.id,
            "user_id": p.user_id,
            "user_name": user_name,
            "role": p.role,
            "department": p.department,
            "access_level": p.access_level,
            "granted_by_name": granted_by_name,
            "granted_at": p.granted_at,
            "expires_at": p.expires_at,
        })
    return out


def remove_document_permission(db, doc_id: str, perm_id: str):
    perm = db.query(DocumentPermission).filter(
        and_(
            DocumentPermission.id == perm_id,
            DocumentPermission.document_id == doc_id,
        )
    ).first()
    if not perm:
        raise HTTPException(status_code=404, detail="Permission not found")
    db.delete(perm)
    db.commit()


def approve_document(db, doc, payload, current_user):
    if not doc.requires_approval:
        raise HTTPException(status_code=400, detail="This document does not require approval")

    if doc.approval_request_id:
        # Route through the multi-level workflow engine
        from app.services.approval_engine import decide_approval_request
        decision_str = payload.status.value if hasattr(payload.status, 'value') else str(payload.status)
        note = getattr(payload, 'note', None) or getattr(payload, 'notes', None)
        decide_approval_request(doc.approval_request_id, decision_str, note, None, db, current_user)
        db.refresh(doc)
        return serialize_document(db, doc, current_user)

    # Legacy path: no workflow linked — direct approval
    doc.approval_status = payload.status
    if payload.status == ApprovalStatus.approved:
        doc.approved_by = current_user.id
        doc.approved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(doc)
    return serialize_document(db, doc, current_user)


def submit_for_approval(db, doc, current_user):
    """Submit a document for approval.

    Allowed when:
      - The document requires approval AND has no current request, OR
      - The previous request finished as rejected (resubmission case). The old
        request is preserved as history; the document is reset to pending and a
        new ApprovalRequest is opened.
    """
    if not doc.requires_approval:
        raise HTTPException(status_code=400, detail="This document does not require approval")

    if doc.approval_request_id:
        from app.models.billing_reports import ApprovalRequest as ARModel
        prev = db.get(ARModel, doc.approval_request_id)
        prev_status = (getattr(prev, "status", None) or "").lower() if prev else None
        if prev and prev_status not in ("rejected", "cancelled"):
            raise HTTPException(status_code=409, detail="Document already has an active approval request")
        # Reset document to allow a fresh submission. The previous request stays
        # in the DB as audit trail; we just unlink it from the document.
        doc.approval_request_id = None
        doc.approval_status = ApprovalStatus.pending
        doc.approved_by = None
        doc.approved_at = None
        db.add(doc)
        db.flush()

    ar_id = _auto_create_approval_request(db, doc, current_user)
    if not ar_id:
        raise HTTPException(
            status_code=422,
            detail="No approval workflow configured for this document category. "
                   "Please configure a workflow in Settings > Approval Workflows.",
        )
    db.commit()
    db.refresh(doc)
    return serialize_document(db, doc, current_user)


def create_and_upload_document(db, current_user, file, content: bytes, title: str, description, category: str,
                                project_id, client_id, task_id, ticket_id, requires_approval: bool,
                                tags, change_note, s3_key: str, file_size: int):
    try:
        cat_enum = DocumentCategory(category)
    except ValueError:
        cat_enum = DocumentCategory.other
    doc = Document(
        title=title,
        description=description,
        category=cat_enum,
        project_id=project_id or None,
        client_id=client_id or None,
        task_id=task_id or None,
        ticket_id=ticket_id or None,
        requires_approval=requires_approval,
        created_by=current_user.id,
    )
    db.add(doc)
    db.flush()
    version = DocumentVersion(
        document_id=doc.id,
        version_num=1,
        file_key=s3_key,
        file_name=file.filename or "document",
        file_size=file_size,
        file_mime_type=file.content_type,
        change_note=change_note or "Initial version",
        created_by=current_user.id,
    )
    db.add(version)
    if tags:
        for tag in [t.strip() for t in tags.split(",") if t.strip()]:
            db.add(DocumentTag(document_id=doc.id, tag_name=tag))
    if requires_approval:
        _auto_create_approval_request(db, doc, current_user)
    db.commit()
    db.refresh(doc)
    return serialize_document(db, doc, current_user)


def resolve_user_from_token(db, token: str):
    payload = decode_token(token)
    if payload and payload.get("type") == "access":
        user_id = payload.get("sub")
        return db.query(User).filter(User.id == user_id, User.is_active == True).first()
    return None


def get_version_by_file_key(db, file_key: str):
    return db.query(DocumentVersion).filter(DocumentVersion.file_key == file_key).first()


def log_document_download(db, doc_id: str, user_id: str, ip_address):
    db.add(DocumentAccessLog(document_id=doc_id, user_id=user_id, action="download", ip_address=ip_address))
    db.commit()


def docs_by_project(db, project_id: str, archived: bool):
    return db.query(Document).filter(
        Document.project_id == project_id,
        Document.is_archived == archived,
    ).order_by(Document.created_at.desc()).all()


def docs_by_task(db, task_id: str):
    return db.query(Document).filter(
        Document.task_id == task_id,
        Document.is_archived == False,
    ).order_by(Document.created_at.desc()).all()


def docs_by_ticket(db, ticket_id: str):
    return db.query(Document).filter(
        Document.ticket_id == ticket_id,
        Document.is_archived == False,
    ).order_by(Document.created_at.desc()).all()


def add_tag(db, doc_id: str, tag_name: str):
    db.add(DocumentTag(document_id=doc_id, tag_name=tag_name))
    db.commit()


def remove_tag(db, doc_id: str, tag_name: str):
    tag = db.query(DocumentTag).filter(
        DocumentTag.document_id == doc_id,
        DocumentTag.tag_name == tag_name,
    ).first()
    if not tag:
        raise HTTPException(404, "Tag not found")
    db.delete(tag)
    db.commit()


def save_ai_summary(db, doc, summary_text: str):
    doc.ai_summary = summary_text
    db.commit()
