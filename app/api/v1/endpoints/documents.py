"""
Document Management API Endpoints.
Handles CRUD operations, versioning, permissions, and file uploads.
Works with both S3 (when configured) and local filesystem storage.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Body, Form, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from datetime import datetime, timezone, timedelta
from typing import List, Optional
import logging
import mimetypes

from app.core.deps import get_db, get_current_user
from app.core.config import settings
from app.core.abac_enforce import enforce_abac
from app.models.user import User
from app.models.documents import (
    Document, DocumentVersion, DocumentPermission, DocumentTag,
    DocumentCategory, DocumentAccessLevel, ApprovalStatus, DocumentAccessLog
)
from app.schemas.documents import (
    DocumentCreate, DocumentUpdate, DocumentOut, DocumentListOut, DocumentVersionOut,
    DocumentPermissionCreate, DocumentPermissionOut, DocumentApprovalPayload
)
from app.services.s3_service import file_storage
from app.services.pagination_service import paginate_query
from app.services.ai_dispatch import call_ai
from app.services import documents_service as doc_svc

router = APIRouter(prefix="/documents", tags=["documents"])
logger = logging.getLogger(__name__)

# P0-2: MIME type whitelist — blocks executables and dangerous file types
ALLOWED_MIME_TYPES = {
    # Documents
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.oasis.opendocument.text",
    "application/vnd.oasis.opendocument.spreadsheet",
    "text/plain",
    "text/csv",
    "text/markdown",
    "application/json",
    "application/xml",
    "text/xml",
    # Images
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/svg+xml",
    "image/tiff",
    # Video / audio (for meeting recordings)
    "video/mp4",
    "video/webm",
    "audio/mpeg",
    "audio/mp4",
    "audio/webm",
}

ALLOWED_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".odt", ".ods", ".txt", ".csv", ".md", ".json", ".xml",
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".tiff", ".tif",
    ".mp4", ".webm", ".mp3", ".m4a",
}

BLOCKED_MAGIC_BYTES = {
    b"MZ",          # Windows PE exe/dll
    b"\x7fELF",     # Linux ELF binary
    b"\xfe\xed\xfa\xce",  # macOS Mach-O binary
    b"\xfe\xed\xfa\xcf",  # macOS Mach-O binary (64-bit)
    b"#!/",         # Shell script
    b"#!",          # Shebang
}

BLOCKED_ARCHIVE_EXTENSIONS = {".zip", ".gz", ".tar", ".tgz", ".7z", ".rar"}


_detect_mime_from_magic = doc_svc.detect_mime_from_magic


_validate_upload = doc_svc.validate_upload


# ── Helper Functions ───────────────────────────────────────────────────────

get_document_or_404   = doc_svc.get_document_or_404
check_document_access = doc_svc.check_document_access


serialize_document = doc_svc.serialize_document


# ── CRUD Endpoints ─────────────────────────────────────────────────────────

@router.post("", response_model=DocumentOut, summary="Create document")
def create_document(
    payload: DocumentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create new document."""
    enforce_abac(db, current_user, "document", action="create")
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
    db.commit()
    db.refresh(doc)
    return serialize_document(db, doc, current_user)


@router.get("", response_model=List[DocumentListOut], summary="List documents with filters")
def list_documents(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    category: Optional[DocumentCategory] = None,
    tags: Optional[str] = None,
    search: Optional[str] = None,
    project_id: Optional[str] = None,
    is_archived: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List documents with optional filters."""
    q = db.query(Document).filter(Document.is_archived == is_archived)

    # Apply filters
    if category:
        q = q.filter(Document.category == category)
    if project_id:
        q = q.filter(Document.project_id == project_id)
    if search:
        q = q.filter(or_(
            Document.title.ilike(f"%{search}%"),
            Document.description.ilike(f"%{search}%"),
        ))

    # Role-based filtering
    from app.models.user import UserRole
    if current_user.role != UserRole.admin:
        # Non-admins: only documents they created or have explicit permission
        q = q.filter(or_(
            Document.created_by == current_user.id,
            Document.permissions.any(DocumentPermission.user_id == current_user.id),
        ))

    if not current_user.is_superadmin and current_user.organization_id:
        org_user_ids = db.query(User.id).filter(
            User.organization_id == current_user.organization_id
        ).scalar_subquery()
        q = q.filter(
            or_(
                Document.created_by.in_(org_user_ids),
                Document.permissions.any(DocumentPermission.user_id.in_(org_user_ids)),
            )
        )

    q = q.order_by(Document.created_at.desc()).offset(skip).limit(limit)
    docs = q.all()

    result = []
    for doc in docs:
        latest_version = doc.versions[0] if doc.versions else None

        # Only include version info if there are versions
        version_data = None
        if latest_version:
            _url = file_storage.generate_presigned_url(latest_version.file_key) if latest_version.file_key else None
            version_data = DocumentVersionOut(
                id=latest_version.id,
                version_num=latest_version.version_num,
                file_name=latest_version.file_name,
                file_size=latest_version.file_size,
                file_mime_type=latest_version.file_mime_type,
                change_note=latest_version.change_note,
                uploader_id=latest_version.created_by,
                uploader_name=latest_version.uploader.full_name if latest_version.uploader else "Unknown",
                created_at=latest_version.created_at,
                download_url=_url,
                s3_url=_url,
            )

        result.append(DocumentListOut(
            id=doc.id,
            title=doc.title,
            category=doc.category,
            is_archived=doc.is_archived,
            approval_status=doc.approval_status,
            created_by_name=doc.creator.full_name if doc.creator else "Unknown",
            created_at=doc.created_at,
            updated_at=doc.updated_at,
            latest_version=version_data,
        ))

    return result


@router.get("/{doc_id}", response_model=DocumentOut, summary="Get document detail")
def get_document(
    doc_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get document with full details and version history."""
    enforce_abac(db, current_user, "document", doc_id, action="read")
    doc = get_document_or_404(db, doc_id)
    check_document_access(doc, current_user)
    # Audit trail
    db.add(DocumentAccessLog(
        document_id=doc.id,
        user_id=current_user.id,
        action="view",
        ip_address=request.client.host if request.client else None,
    ))
    db.commit()
    return serialize_document(db, doc, current_user)


@router.patch("/{doc_id}", response_model=DocumentOut, summary="Update document metadata")
def update_document(
    doc_id: str,
    payload: DocumentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update document metadata (title, category, etc)."""
    doc = get_document_or_404(db, doc_id)
    check_document_access(doc, current_user, DocumentAccessLevel.editor)

    # Update fields
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(doc, field, value)

    doc.updated_by = current_user.id
    db.commit()
    db.refresh(doc)
    return serialize_document(db, doc, current_user)


@router.delete("/{doc_id}", summary="Archive document (soft delete)")
def delete_document(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Soft delete document (mark as archived)."""
    doc = get_document_or_404(db, doc_id)
    check_document_access(doc, current_user, DocumentAccessLevel.admin)

    doc.is_archived = True
    db.commit()
    return {"status": "archived"}


# ── Version Management ─────────────────────────────────────────────────────

@router.post("/{doc_id}/versions", response_model=DocumentVersionOut, summary="Upload new document version")
def upload_version(
    doc_id: str,
    file: UploadFile = File(...),
    change_note: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload new version of document."""
    doc = get_document_or_404(db, doc_id)
    check_document_access(doc, current_user, DocumentAccessLevel.editor)

    # Check file size (convert MB to bytes)
    max_file_size_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    content = file.file.read(max_file_size_bytes + 1)
    if len(content) > max_file_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large (max {settings.MAX_FILE_SIZE_MB}MB)"
        )
    # content already holds the complete file bytes — no need to re-read

    # P0-2: Validate MIME type and magic bytes
    _validate_upload(file.filename or "", file.content_type or "", content)

    # Upload file (S3 when configured, local filesystem otherwise)
    try:
        s3_key, file_size = file_storage.upload_file(
            file_content=content,
            file_name=file.filename,
            document_id=doc_id,
            version_num=len(doc.versions) + 1,
            content_type=file.content_type or "application/octet-stream",
        )
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Create version record
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
        # Prevent storage/DB split-brain when upload succeeds but DB fails.
        try:
            file_storage.delete_file(s3_key)
        except Exception:
            logger.warning("Failed to cleanup orphaned uploaded file key %s", s3_key, exc_info=True)
        raise
    db.refresh(version)

    return DocumentVersionOut(
        id=version.id,
        version_num=version.version_num,
        file_name=version.file_name,
        file_size=version.file_size,
        file_mime_type=version.file_mime_type,
        change_note=version.change_note,
        uploader_id=version.created_by,
        uploader_name=current_user.full_name,
        created_at=version.created_at,
        download_url=file_storage.generate_presigned_url(s3_key) if s3_key else None,
        s3_url=file_storage.generate_presigned_url(s3_key) if s3_key else None,
    )


@router.get("/{doc_id}/versions", response_model=List[DocumentVersionOut], summary="Get version history")
def get_versions(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all versions of a document."""
    doc = get_document_or_404(db, doc_id)
    check_document_access(doc, current_user)

    return [DocumentVersionOut(
        id=v.id,
        version_num=v.version_num,
        file_name=v.file_name,
        file_size=v.file_size,
        file_mime_type=v.file_mime_type,
        change_note=v.change_note,
        uploader_id=v.created_by,
        uploader_name=v.uploader.full_name if v.uploader else "Unknown",
        created_at=v.created_at,
        download_url=file_storage.generate_presigned_url(v.file_key) if v.file_key else None,
        s3_url=file_storage.generate_presigned_url(v.file_key) if v.file_key else None,
    ) for v in doc.versions]


# ── Permission Management ──────────────────────────────────────────────────

@router.post("/{doc_id}/permissions", response_model=DocumentPermissionOut, summary="Grant document access")
def add_permission(
    doc_id: str,
    payload: DocumentPermissionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Grant access to document for a user."""
    doc = get_document_or_404(db, doc_id)
    check_document_access(doc, current_user, DocumentAccessLevel.admin)

    # Check if user exists
    user = db.query(User).filter(User.id == payload.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Check for duplicate permission
    existing = db.query(DocumentPermission).filter(
        and_(
            DocumentPermission.document_id == doc_id,
            DocumentPermission.user_id == payload.user_id,
        )
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="User already has access to this document")

    perm = DocumentPermission(
        document_id=doc_id,
        user_id=payload.user_id,
        access_level=payload.access_level,
        granted_by=current_user.id,
        expires_at=payload.expires_at,
    )
    db.add(perm)
    db.commit()
    db.refresh(perm)

    return DocumentPermissionOut(
        id=perm.id,
        user_id=perm.user_id,
        user_name=user.full_name,
        access_level=perm.access_level,
        granted_by_name=current_user.full_name,
        granted_at=perm.granted_at,
        expires_at=perm.expires_at,
    )


@router.delete("/{doc_id}/permissions/{perm_id}", summary="Revoke document access")
def remove_permission(
    doc_id: str,
    perm_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Revoke user access to document."""
    doc = get_document_or_404(db, doc_id)
    check_document_access(doc, current_user, DocumentAccessLevel.admin)

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
    return {"status": "revoked"}


# ── Approval Workflow ──────────────────────────────────────────────────────

@router.post("/{doc_id}/approve", response_model=DocumentOut, summary="Approve document")
def approve_document(
    doc_id: str,
    payload: DocumentApprovalPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Approve or reject document."""
    doc = get_document_or_404(db, doc_id)
    check_document_access(doc, current_user, DocumentAccessLevel.admin)

    if not doc.requires_approval:
        raise HTTPException(status_code=400, detail="This document does not require approval")

    doc.approval_status = payload.status
    if payload.status == ApprovalStatus.approved:
        doc.approved_by = current_user.id
        doc.approved_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(doc)
    return serialize_document(db, doc, current_user)


# ── Combined create + upload in one request ────────────────────────────────

@router.post("/upload", summary="Create document and upload file in one step")
def create_and_upload(
    file: UploadFile = File(...),
    title: str = Form(...),
    description: Optional[str] = Form(None),
    category: str = Form("other"),
    project_id: Optional[str] = Form(None),
    client_id: Optional[str] = Form(None),
    task_id: Optional[str] = Form(None),
    ticket_id: Optional[str] = Form(None),
    requires_approval: bool = Form(False),
    tags: Optional[str] = Form(None),
    change_note: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a document record and upload the first file version in a single multipart request."""
    enforce_abac(db, current_user, "document", action="create")
    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    content = file.file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(413, f"File exceeds maximum size of {settings.MAX_FILE_SIZE_MB} MB")

    # P0-2: Validate MIME type and magic bytes
    _validate_upload(file.filename or "", file.content_type or "", content)

    # Validate category
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
    db.add(doc); db.flush()

    # Upload file
    try:
        file_key, file_size = file_storage.upload_file(
            file_content=content,
            file_name=file.filename or "document",
            document_id=doc.id,
            version_num=1,
            content_type=file.content_type or "application/octet-stream",
        )
    except Exception as exc:
        db.rollback()
        raise HTTPException(500, f"File upload failed: {str(exc)[:200]}")

    version = DocumentVersion(
        document_id=doc.id,
        version_num=1,
        file_key=file_key,
        file_name=file.filename or "document",
        file_size=file_size,
        file_mime_type=file.content_type,
        change_note=change_note or "Initial version",
        created_by=current_user.id,
    )
    db.add(version)

    # Tags
    if tags:
        for tag in [t.strip() for t in tags.split(",") if t.strip()]:
            db.add(DocumentTag(document_id=doc.id, tag_name=tag))

    db.commit(); db.refresh(doc)
    return serialize_document(db, doc, current_user)


# ── Serve local files ──────────────────────────────────────────────────────

@router.get("/file/{file_key:path}", summary="Download / stream a locally stored document file")
def serve_local_file(
    file_key: str,
    request: Request,
    token: Optional[str] = Query(default=None, description="JWT access token (for browser-native requests that cannot set Authorization header)"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """Serve a file stored on the local filesystem.

    The file_key is the relative path returned by LocalFileStorage (e.g.
    ``documents/{doc_id}/v1/abc123.pdf``).  Not used when S3 is active
    (those URLs are direct pre-signed S3 links).

    Access control: verifies the requesting user has at least viewer access
    to the document that owns this file version.

    Authentication: accepts either the standard ``Authorization: Bearer`` header
    or a ``?token=`` query parameter (required for browser-native iframe/img tags).
    """
    # Fall back to query-param token when browser can't set Authorization header
    if current_user is None and token:
        from app.core.security import decode_token
        payload = decode_token(token)
        if payload and payload.get("type") == "access":
            user_id = payload.get("sub")
            current_user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if current_user is None:
        raise HTTPException(status_code=401, detail="No autenticado")
    from app.services.s3_service import LocalFileStorage
    if not isinstance(file_storage, LocalFileStorage):
        raise HTTPException(404, "Direct file serving only available in local-storage mode")

    # Verify the user has access to the document that owns this file key
    version = db.query(DocumentVersion).filter(DocumentVersion.file_key == file_key).first()
    if not version:
        raise HTTPException(404, "File not found")
    doc = get_document_or_404(db, version.document_id)
    check_document_access(doc, current_user)  # raises 403 if no access

    try:
        content = file_storage.get_file_bytes(file_key)
    except PermissionError:
        raise HTTPException(403, "Access denied")
    except FileNotFoundError:
        raise HTTPException(404, "File not found")

    mime_type, _ = mimetypes.guess_type(file_key)
    mime_type = mime_type or "application/octet-stream"
    filename = file_key.split("/")[-1]

    # Audit trail for file download
    db.add(DocumentAccessLog(
        document_id=doc.id,
        user_id=current_user.id,
        action="download",
        ip_address=request.client.host if request.client else None,
    ))
    db.commit()
    # SVG served inline allows JS execution (XSS); force download for SVG
    disposition = "attachment" if mime_type == "image/svg+xml" else "inline"
    return StreamingResponse(
        iter([content]),
        media_type=mime_type,
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )


# ── Documents filtered by entity ──────────────────────────────────────────

@router.get("/by-project/{project_id}", summary="List documents linked to a project")
def docs_by_project(
    project_id: str,
    archived: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    response: Response = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Document).filter(
        Document.project_id == project_id,
        Document.is_archived == archived,
    ).order_by(Document.created_at.desc())
    docs, _, _ = paginate_query(q, page, page_size, response)
    return _doc_list(db, docs)


@router.get("/by-task/{task_id}", summary="List documents linked to a task")
def docs_by_task(
    task_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    docs = db.query(Document).filter(
        Document.task_id == task_id,
        Document.is_archived == False,
    ).order_by(Document.created_at.desc()).all()
    return _doc_list(db, docs)


@router.get("/by-ticket/{ticket_id}", summary="List documents linked to a ticket")
def docs_by_ticket(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    docs = db.query(Document).filter(
        Document.ticket_id == ticket_id,
        Document.is_archived == False,
    ).order_by(Document.created_at.desc()).all()
    return _doc_list(db, docs)


_doc_list = lambda db, docs: doc_svc.build_doc_list(docs)


# ── Tag management ─────────────────────────────────────────────────────────

@router.post("/{doc_id}/tags", summary="Add tag to document")
def add_tag(
    doc_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = get_document_or_404(db, doc_id)
    check_document_access(doc, current_user, DocumentAccessLevel.editor)
    tag_name = (payload.get("tag") or "").strip().lower()
    if not tag_name:
        raise HTTPException(400, "tag required")
    if any(t.tag_name == tag_name for t in doc.tags):
        raise HTTPException(409, "Tag already exists")
    db.add(DocumentTag(document_id=doc_id, tag_name=tag_name))
    db.commit()
    return {"ok": True}


@router.delete("/{doc_id}/tags/{tag_name}", summary="Remove tag from document")
def remove_tag(
    doc_id: str,
    tag_name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = get_document_or_404(db, doc_id)
    check_document_access(doc, current_user, DocumentAccessLevel.editor)
    tag = db.query(DocumentTag).filter(
        DocumentTag.document_id == doc_id,
        DocumentTag.tag_name == tag_name,
    ).first()
    if not tag:
        raise HTTPException(404, "Tag not found")
    db.delete(tag); db.commit()
    return {"ok": True}


# ── AI document summary ────────────────────────────────────────────────────

@router.post("/{doc_id}/ai-summary", summary="Generate AI summary for a document")
def ai_summary(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Use the configured AI provider to generate a short summary of the document.

    Only works for text-extractable files (PDF text layer, .txt, .md).
    The latest version is used.
    """
    doc = get_document_or_404(db, doc_id)
    check_document_access(doc, current_user)

    if not doc.versions:
        raise HTTPException(400, "Document has no versions to summarise")

    latest = doc.versions[0]
    if not latest.file_key:
        raise HTTPException(400, "No file attached to latest version")

    text_content = doc_svc.extract_document_text(latest.file_key, latest.file_name or "", latest.file_mime_type or "")

    if not text_content:
        # Fallback: summarise from metadata only
        text_content = (
            f"Document: {doc.title}\n"
            f"Category: {doc.category}\n"
            f"Description: {doc.description or 'None'}\n"
            f"File: {latest.file_name} ({latest.file_mime_type})"
        )

    try:
        summary_text = call_ai(
            db,
            messages=[{"role": "user", "content": f"Genera un resumen ejecutivo conciso (mximo 150 palabras) de este documento:\n\n{text_content}"}],
            system="Eres un asistente experto en anlisis de documentos empresariales. Responde en el idioma del documento.",
            module="document_summary",
            user_id=current_user.id,
            max_tokens=300,
        )
    except Exception as exc:
        raise HTTPException(503, f"AI summary unavailable: {str(exc)[:100]}")

    # Store in description if empty
    if not doc.description:
        doc.description = summary_text
        db.commit()

    return {"document_id": doc_id, "summary": summary_text}
