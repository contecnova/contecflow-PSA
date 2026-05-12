"""
Document Management API Endpoints.
Handles CRUD operations, versioning, permissions, and file uploads.
Works with both S3 (when configured) and local filesystem storage.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Body, Form, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional
import logging
import mimetypes

from app.core.deps import get_db, get_current_user
from app.core.config import settings
from app.core.abac_enforce import enforce_abac
from app.models.user import User
from app.models.documents import (
    DocumentCategory, DocumentAccessLevel
)
from app.schemas.documents import (
    DocumentCreate, DocumentUpdate, DocumentOut, DocumentListOut, DocumentVersionOut,
    DocumentPermissionCreate, DocumentPermissionOut, DocumentApprovalPayload
)
from app.services.s3_service import file_storage
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
    return doc_svc.create_document(db, payload, current_user)



@router.get("", response_model=List[DocumentListOut], summary="List documents with filters")
def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    category: Optional[DocumentCategory] = None,
    tags: Optional[str] = None,
    search: Optional[str] = None,
    project_id: Optional[str] = None,
    is_archived: bool = False,
    response: Response = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List documents with optional filters and paginación obligatoria."""
    docs_q, total = doc_svc.query_documents(db, current_user, category, tags, search, project_id, is_archived)
    docs = docs_q.offset((page - 1) * page_size).limit(page_size).all()
    if response is not None:
        response.headers["X-Total-Count"] = str(total)
        response.headers["X-Page"] = str(page)
        response.headers["X-Page-Size"] = str(page_size)
    return [doc_svc.serialize_doc_list_item(doc) for doc in docs]


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
    doc_svc.log_document_view(db, doc.id, current_user.id, request.client.host if request.client else None)
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
    return doc_svc.update_document(db, doc, payload, current_user)


@router.delete("/{doc_id}", summary="Archive document (soft delete)")
def delete_document(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Soft delete document (mark as archived)."""
    enforce_abac(db, current_user, "document", doc_id, action="delete")
    doc = get_document_or_404(db, doc_id)
    check_document_access(doc, current_user, DocumentAccessLevel.admin)
    doc_svc.archive_document(db, doc)
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
    except ValueError as exc:
        # ValueError aquí indica rechazo del backend de almacenamiento por la
        # entrada (tipo no permitido, key inválido…), por lo que es un error
        # del cliente, no un fallo del servidor.
        logger.warning("Storage rejected upload for doc=%s: %s", doc_id, exc)
        raise HTTPException(status_code=400, detail=f"Archivo rechazado por el sistema de almacenamiento: {exc}")

    # Create version record
    try:
        version = doc_svc.create_document_version(db, doc, doc_id, file, content, change_note, current_user, s3_key, file_size)
    except Exception:
        # Prevent storage/DB split-brain when upload succeeds but DB fails.
        try:
            file_storage.delete_file(s3_key)
        except Exception:
            logger.warning("Failed to cleanup orphaned uploaded file key %s", s3_key, exc_info=True)
        raise

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
    """Grant access to document — by user, role or department (exactly one)."""
    doc = get_document_or_404(db, doc_id)
    check_document_access(doc, current_user, DocumentAccessLevel.admin)

    perm, user = doc_svc.add_document_permission(db, doc_id, payload, current_user)
    return DocumentPermissionOut(
        id=perm.id,
        user_id=perm.user_id,
        user_name=user.full_name if user else None,
        role=perm.role,
        department=perm.department,
        access_level=perm.access_level,
        granted_by_name=current_user.full_name,
        granted_at=perm.granted_at,
        expires_at=perm.expires_at,
    )


@router.get("/{doc_id}/permissions", response_model=list[DocumentPermissionOut], summary="List document permissions")
def list_permissions(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List explicit grants on this document."""
    doc = get_document_or_404(db, doc_id)
    check_document_access(doc, current_user, DocumentAccessLevel.viewer)
    return doc_svc.list_document_permissions(db, doc_id)


@router.delete("/{doc_id}/permissions/{perm_id}", summary="Revoke document access")
def remove_permission(
    doc_id: str,
    perm_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Revoke user access to document."""
    enforce_abac(db, current_user, "document_permission", perm_id, action="delete")
    doc = get_document_or_404(db, doc_id)
    check_document_access(doc, current_user, DocumentAccessLevel.admin)

    doc_svc.remove_document_permission(db, doc_id, perm_id)
    return {"status": "revoked"}


# ── Approval Workflow ──────────────────────────────────────────────────────

@router.post("/{doc_id}/approve", response_model=DocumentOut, summary="Approve document")
def approve_document(
    doc_id: str,
    payload: DocumentApprovalPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Approve or reject document — routes through multi-level workflow engine when a workflow is linked."""
    doc = get_document_or_404(db, doc_id)
    check_document_access(doc, current_user, DocumentAccessLevel.admin)

    return doc_svc.approve_document(db, doc, payload, current_user)


@router.post("/{doc_id}/submit-approval", response_model=DocumentOut, summary="Submit document for approval")
def submit_for_approval(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Explicitly open an approval request for a document that requires_approval=True but has no active workflow yet."""
    doc = get_document_or_404(db, doc_id)
    check_document_access(doc, current_user, DocumentAccessLevel.editor)

    return doc_svc.submit_for_approval(db, doc, current_user)


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
        DocumentCategory(category)
    except ValueError:
        pass

    # Upload file
    try:
        file_key, file_size = file_storage.upload_file(
            file_content=content,
            file_name=file.filename or "document",
            document_id="pending",
            version_num=1,
            content_type=file.content_type or "application/octet-stream",
        )
    except Exception as exc:
        # Fallo upstream del backend de almacenamiento (S3 / FS) — no es un
        # error de la petición del cliente, sino indisponibilidad del servicio.
        logger.exception("File upload to storage failed for user=%s file=%s", current_user.id, file.filename)
        raise HTTPException(
            status_code=503,
            detail="El servicio de almacenamiento no está disponible temporalmente. Inténtalo de nuevo en unos minutos.",
        )

    return doc_svc.create_and_upload_document(
        db, current_user, file, content, title, description, category,
        project_id, client_id, task_id, ticket_id, requires_approval,
        tags, change_note, file_key, file_size,
    )


# ── Serve local files ──────────────────────────────────────────────────────

@router.get("/file/{file_key:path}", summary="Download / stream a locally stored document file")
def serve_local_file(
    file_key: str,
    request: Request,
    access: Optional[str] = Query(default=None, description="Short-lived scoped access token for this file URL"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """Serve a file stored on the local filesystem.

    The file_key is the relative path returned by LocalFileStorage (e.g.
    ``documents/{doc_id}/v1/abc123.pdf``).  Not used when S3 is active
    (those URLs are direct pre-signed S3 links).

    Access control: verifies the requesting user has at least viewer access
    to the document that owns this file version.

    Authentication: accepts either the standard session/auth header/cookie
    or a short-lived scoped ``?access=`` token generated with the download URL.
    """
    token_ok = bool(access and doc_svc.resolve_file_access_token(access, file_key))
    if current_user is None and not token_ok:
        raise HTTPException(status_code=401, detail="No autenticado")
    from app.services.s3_service import LocalFileStorage
    if not isinstance(file_storage, LocalFileStorage):
        raise HTTPException(404, "Direct file serving only available in local-storage mode")

    # Verify the file exists and access constraints.
    version = doc_svc.get_version_by_file_key(db, file_key)
    if not version:
        raise HTTPException(404, "File not found")
    if current_user is not None:
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
    if current_user is not None:
        doc_svc.log_document_download(db, doc.id, current_user.id, request.client.host if request.client else None)
    # SVG served inline allows JS execution (XSS); force download for SVG
    disposition = "attachment" if mime_type == "image/svg+xml" else "inline"
    return StreamingResponse(
        iter([content]),
        media_type=mime_type,
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )


@router.head("/file/{file_key:path}", summary="Probe metadata for a locally stored document file")
def head_local_file(
    file_key: str,
    access: Optional[str] = Query(default=None, description="Short-lived scoped access token for this file URL"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """Return metadata headers for a locally stored file without streaming the body."""
    token_ok = bool(access and doc_svc.resolve_file_access_token(access, file_key))
    if current_user is None and not token_ok:
        raise HTTPException(status_code=401, detail="No autenticado")
    from app.services.s3_service import LocalFileStorage
    if not isinstance(file_storage, LocalFileStorage):
        raise HTTPException(404, "Direct file serving only available in local-storage mode")

    version = doc_svc.get_version_by_file_key(db, file_key)
    if not version:
        raise HTTPException(404, "File not found")
    if current_user is not None:
        doc = get_document_or_404(db, version.document_id)
        check_document_access(doc, current_user)

    file_size = file_storage.get_file_size(file_key)
    if file_size is None:
        raise HTTPException(404, "File not found")

    mime_type, _ = mimetypes.guess_type(file_key)
    mime_type = mime_type or "application/octet-stream"
    filename = file_key.split("/")[-1]
    disposition = "attachment" if mime_type == "image/svg+xml" else "inline"

    return Response(
        status_code=200,
        headers={
            "Content-Type": mime_type,
            "Content-Disposition": f'{disposition}; filename="{filename}"',
            "Content-Length": str(file_size),
        },
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
    docs_q, total = doc_svc.query_documents(db, current_user, project_id=project_id, is_archived=archived)
    docs = docs_q.offset((page - 1) * page_size).limit(page_size).all()
    if response is not None:
        response.headers["X-Total-Count"] = str(total)
        response.headers["X-Page"] = str(page)
        response.headers["X-Page-Size"] = str(page_size)
    return [doc_svc.serialize_doc_list_item(doc) for doc in docs]



@router.get("/by-task/{task_id}", summary="List documents linked to a task")
def docs_by_task(
    task_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    response: Response = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    docs_q, total = doc_svc.query_documents(db, current_user, task_id=task_id)
    docs = docs_q.offset((page - 1) * page_size).limit(page_size).all()
    if response is not None:
        response.headers["X-Total-Count"] = str(total)
        response.headers["X-Page"] = str(page)
        response.headers["X-Page-Size"] = str(page_size)
    return [doc_svc.serialize_doc_list_item(doc) for doc in docs]



@router.get("/by-ticket/{ticket_id}", summary="List documents linked to a ticket")
def docs_by_ticket(
    ticket_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    response: Response = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        docs_q, total = doc_svc.query_documents(db, current_user, ticket_id=ticket_id)
        docs = docs_q.offset((page - 1) * page_size).limit(page_size).all()
        if response is not None:
            response.headers["X-Total-Count"] = str(total)
            response.headers["X-Page"] = str(page)
            response.headers["X-Page-Size"] = str(page_size)
        return [doc_svc.serialize_doc_list_item(doc) for doc in docs]
    except Exception:
        logger.exception("docs_by_ticket failed for ticket_id=%s", ticket_id)
        if response is not None:
            response.headers["X-Total-Count"] = "0"
            response.headers["X-Page"] = str(page)
            response.headers["X-Page-Size"] = str(page_size)
        return []


def _doc_list(db, docs):
    return doc_svc.build_doc_list(docs)


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
    doc_svc.add_tag(db, doc_id, tag_name)
    return {"ok": True}


@router.delete("/{doc_id}/tags/{tag_name}", summary="Remove tag from document")
def remove_tag(
    doc_id: str,
    tag_name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    enforce_abac(db, current_user, "document_tag", f"{doc_id}:{tag_name}", action="delete")
    doc = get_document_or_404(db, doc_id)
    check_document_access(doc, current_user, DocumentAccessLevel.editor)
    doc_svc.remove_tag(db, doc_id, tag_name)
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
        raise HTTPException(
            422,
            (
                "No se pudo extraer texto del documento. "
                "Sube una version con capa de texto o habilita OCR (tesseract + pytesseract + pypdfium2)."
            ),
        )

    visual_marker = "[ANALISIS_VISUAL]"
    is_visual_source = isinstance(text_content, str) and text_content.startswith(visual_marker)
    source_payload = text_content.replace(visual_marker, "", 1).strip() if is_visual_source else text_content

    user_prompt = (
        (
            "Genera una descripcion visual panoramica (entre 180 y 320 palabras, en 2-4 parrafos) "
            "a partir del analisis visual proporcionado, indicando: "
            "(1) que tipo de imagen o documento visual parece ser, "
            "(2) que elementos visuales principales contiene, "
            "(3) para que podria servir dentro de un contexto empresarial, "
            "(4) si hay texto parcial OCR, que sugiere de forma general. "
            "Si hay incertidumbre, dilo explicitamente sin inventar detalles. "
            "El objetivo es ayudar a decidir si merece abrir/revisar el archivo completo.\n\n"
            "Analisis visual:\n" + source_payload
        )
        if is_visual_source else
        (
            "Genera un resumen panorámico (entre 250 y 400 palabras, en 3-5 párrafos) "
            "de este documento, indicando: (1) qué tipo de documento es, "
            "(2) cuál es su propósito y a qué área de negocio aplica, "
            "(3) qué temas o secciones cubre a alto nivel, "
            "(4) por qué tendría utilidad consultarlo. "
            "El objetivo es ayudar a alguien a decidir si abrir el documento sin tener que leerlo.\n\n"
            "Documento:\n" + source_payload
        )
    )

    system_prompt = (
        (
            "Eres un asistente experto en descripcion visual de documentos empresariales. "
            "Responde siempre en espanol claro. "
            "No inventes detalles no soportados por el analisis de entrada; expresa la incertidumbre cuando aplique. "
            "No incluyas datos sensibles ni suposiciones de personas concretas, importes exactos, fechas concretas, "
            "nombres reales de clientes/proveedores o identificadores privados."
        )
        if is_visual_source else
        (
            "Eres un asistente experto en análisis de documentos empresariales. "
            "Responde SIEMPRE en el idioma del documento. "
            "REGLA DE PRIVACIDAD ESTRICTA: NO incluyas en el resumen ningún dato sensible "
            "del contenido — específicamente: nombres propios de personas, importes o cifras "
            "concretas, fechas concretas, números de identificación (NIF/IBAN/IDs), nombres "
            "comerciales de clientes/proveedores específicos, ni transcribas literalmente "
            "cláusulas, condiciones o párrafos. Habla siempre a alto nivel y en términos "
            "genéricos (\"el cliente\", \"el importe pactado\", \"la fecha de vigencia\", etc.). "
            "Si el documento es muy técnico, describe los temas tratados sin reproducir "
            "fórmulas, parámetros o configuraciones específicas."
        )
    )

    try:
        summary_text = call_ai(
            db,
            messages=[{
                "role": "user",
                "content": user_prompt,
            }],
            system=system_prompt,
            module="document_summary",
            user_id=current_user.id,
            max_tokens=700,
        )
    except Exception as exc:
        raise HTTPException(503, f"AI summary unavailable: {str(exc)[:100]}")

    doc_svc.save_ai_summary(db, doc, summary_text)
    return {"document_id": doc_id, "summary": summary_text}
