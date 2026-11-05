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

def _reserva_para(doc, user):
    from app.services.reserva_de_documentos import para_mostrar
    return para_mostrar(doc, user)


def _reserva_vigente(doc):
    from app.services.reserva_de_documentos import vigente
    return vigente(doc)


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
        "checkout": _reserva_vigente(doc),
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
from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy import and_

logger = logging.getLogger(__name__)

# ── MIME / extension config ───────────────────────────────────────────────────
# Auditoría 2026-08 (P1-8): la validación de subidas se movió a
# app/core/uploads.py. Es una preocupación transversal de seguridad, no de este
# dominio: aquí sólo la usaban los 2 endpoints de documentos, mientras los otros
# 4 endpoints con UploadFile del proyecto improvisaban su propia validación (o
# ninguna). Se re-exporta para no romper a los llamadores ni a los tests que la
# importan desde aquí, pero la implementación única vive en el core.
from app.core.uploads import (  # noqa: F401 — re-export por compatibilidad
    ALLOWED_EXTENSIONS,
    ALLOWED_MIME_TYPES,
    BLOCKED_ARCHIVE_EXTENSIONS,
    BLOCKED_MAGIC_BYTES,
    UploadProfile,
    detect_mime_from_magic,
    read_and_validate_upload,
    validate_upload,
)


# ── Document access helpers ───────────────────────────────────────────────────

def get_document_or_404(db, doc_id: str, current_user=None):
    """Fetch a document by id.

    Audit #62: when current_user is supplied and is NOT a superadmin, the
    query is scoped to the user's organization (via Document.created_by ->
    User.organization_id). Returns 404 (not 403) for cross-tenant access
    attempts to avoid leaking existence.
    """
    q = db.query(Document).filter(Document.id == doc_id)
    if current_user is not None and not getattr(current_user, "is_superadmin", False) and getattr(current_user, "organization_id", None):
        org_user_ids = db.query(User.id).filter(
            User.organization_id == current_user.organization_id
        ).scalar_subquery()
        q = q.filter(Document.created_by.in_(org_user_ids))
    doc = q.first()
    if not doc:
        raise HTTPException(404, "Document not found")
    return doc


#: De menos a mas, y el orden ES la jerarquia: la comparacion de niveles se
#: hace por posicion en esta lista.
_NIVELES = [DocumentAccessLevel.viewer, DocumentAccessLevel.editor,
            DocumentAccessLevel.admin]


def _nivel_concedido(doc, user) -> int:
    """La posicion del permiso mas fuerte que aplica a este usuario, o -1.

    Auditoria 2026-09: esto vivia dentro de `check_document_access`, que con
    ello llegaba a complejidad 14. Es una pregunta con nombre propio —«que nivel
    tiene esta persona sobre este documento»— y separarla deja la funcion que
    autoriza en tres lineas legibles.

    Un permiso concede por **uno** de tres sujetos: usuario concreto, rol o
    departamento. Las tres condiciones se comprueban en negativo —«si declara un
    usuario y no es este, fuera»— para que un permiso que declara rol Y
    departamento tenga que cumplir los dos, que es lo que hacia y lo razonable:
    cuanto mas concreto es el permiso, mas condiciones pide.

    Un permiso que no declara ninguno de los tres esta **mal formado** y se
    descarta, no se aplica a todo el mundo. Es la diferencia entre un fallo de
    datos y un agujero.

    Gana el nivel mas alto, no el primero que encaje: si alguien tiene permiso
    de lector por su departamento y de editor por su nombre, es editor.
    """
    rol = user.role.value if hasattr(user.role, "value") else str(user.role)
    departamento = ((user.department or "").strip().lower()
                    if getattr(user, "department", None) else "")
    ahora = datetime.now(timezone.utc)

    mejor = -1
    for permiso in doc.permissions:
        if permiso.user_id and permiso.user_id != user.id:
            continue
        if permiso.role and permiso.role != rol:
            continue
        if permiso.department and permiso.department.strip().lower() != departamento:
            continue
        if not (permiso.user_id or permiso.role or permiso.department):
            continue

        # Las filas guardadas antes de que las fechas llevaran zona se comparan
        # como UTC; sin esto, restar reventaria.
        caduca = (permiso.expires_at
                  if permiso.expires_at is None or permiso.expires_at.tzinfo
                  else permiso.expires_at.replace(tzinfo=timezone.utc))
        if caduca and caduca < ahora:
            continue

        mejor = max(mejor, _NIVELES.index(permiso.access_level))
    return mejor


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

    if _nivel_concedido(doc, user) >= _NIVELES.index(required_level):
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
        checkout=_reserva_para(doc, user),
    )


def _serialize_approval_request(db, doc) -> Optional[dict]:
    """Serialize current approval workflow state for a document."""
    if not getattr(doc, 'approval_request_id', None):
        return None
    try:
        from app.models.billing_reports import ApprovalRequest, ApprovalDecision as ADec
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
            "checkout": _reserva_vigente(doc),
            "latest_version": {
                "id": latest.id, "version_num": latest.version_num, "file_name": latest.file_name,
                "file_size": latest.file_size, "file_mime_type": latest.file_mime_type,
                "download_url": file_storage.generate_presigned_url(latest.file_key) if latest.file_key else None,
            } if latest else None,
        })
    return result


# ── AI summary extraction ─────────────────────────────────────────────────────

_MAX_SUMMARY_SOURCE_CHARS = 8000
_VISUAL_MARKER = "[ANALISIS_VISUAL]"


def _normalize_extracted_text(text: str) -> str:
    """Normalize extracted text and collapse excessive whitespace."""
    normalized = " ".join((text or "").split())
    return normalized[:_MAX_SUMMARY_SOURCE_CHARS]


def _classify_basic_color(rgb: tuple[int, int, int]) -> str:
    palette = {
        "negro": (20, 20, 20),
        "gris": (128, 128, 128),
        "blanco": (235, 235, 235),
        "rojo": (190, 60, 60),
        "naranja": (215, 130, 50),
        "amarillo": (220, 200, 70),
        "verde": (70, 150, 80),
        "azul": (70, 110, 180),
        "morado": (140, 95, 170),
        "marron": (130, 95, 65),
    }
    best_name = "gris"
    best_dist = None
    r, g, b = rgb
    for name, (pr, pg, pb) in palette.items():
        dist = (r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best_name = name
    return best_name


def _describe_pil_image(image, *, file_name: str) -> str:
    from PIL import ImageFilter, ImageStat

    rgb = image.convert("RGB")
    width, height = rgb.size
    orientation = "horizontal" if width > height else ("vertical" if height > width else "cuadrada")

    # Reduce to make statistics stable and fast.
    sample = rgb.resize((min(width, 240), min(height, 240)))
    stat = ImageStat.Stat(sample)
    avg_rgb = tuple(int(v) for v in stat.mean[:3])
    brightness = sum(avg_rgb) / 3.0
    contrast = sum(stat.stddev[:3]) / 3.0

    quantized = sample.quantize(colors=5)
    ranked = sorted((quantized.getcolors() or []), key=lambda x: x[0], reverse=True)
    palette = quantized.getpalette() or []
    dominant = []
    for _count, color_idx in ranked[:3]:
        base = color_idx * 3
        if base + 2 < len(palette):
            name = _classify_basic_color((palette[base], palette[base + 1], palette[base + 2]))
            if name not in dominant:
                dominant.append(name)

    edges = sample.convert("L").filter(ImageFilter.FIND_EDGES)
    edge_strength = ImageStat.Stat(edges).mean[0]
    complexity = "alta" if edge_strength > 38 else ("media" if edge_strength > 20 else "baja")

    brightness_label = "alta" if brightness > 170 else ("media" if brightness > 95 else "baja")
    contrast_label = "alto" if contrast > 55 else ("medio" if contrast > 30 else "bajo")
    colors_label = ", ".join(dominant) if dominant else "sin predominio claro"

    return (
        f"{_VISUAL_MARKER}\n"
        f"Archivo: {file_name or 'imagen'}\n"
        f"Tipo: imagen\n"
        f"Resolucion: {width}x{height} px\n"
        f"Orientacion: {orientation}\n"
        f"Colores dominantes aproximados: {colors_label}\n"
        f"Luminosidad: {brightness_label}\n"
        f"Contraste: {contrast_label}\n"
        f"Complejidad visual: {complexity}\n"
        "Nota: este analisis es visual y aproximado; no usa reconocimiento semantico avanzado de objetos."
    )


def _visual_summary_from_image_bytes(raw: bytes, *, file_name: str) -> str:
    import io
    from PIL import Image

    with Image.open(io.BytesIO(raw)) as image:
        return _describe_pil_image(image, file_name=file_name)


def _visual_summary_from_pdf_first_page(raw: bytes, *, file_name: str) -> str:
    import tempfile

    try:
        import pypdfium2 as pdfium
    except Exception:
        return ""

    with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
        tmp.write(raw)
        tmp.flush()
        pdf = pdfium.PdfDocument(tmp.name)
        if len(pdf) == 0:
            pdf.close()
            return ""
        page = pdf[0]
        bitmap = page.render(scale=1.8)
        pil_image = bitmap.to_pil()
        try:
            summary = _describe_pil_image(pil_image, file_name=file_name)
        finally:
            pil_image.close()
            bitmap.close()
            page.close()
            pdf.close()
        return summary


def _extract_text_from_pdf(raw: bytes, max_pages: int = 10) -> str:
    import io
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(raw))
    chunks = []
    for page in reader.pages[:max_pages]:
        txt = page.extract_text() or ""
        if txt:
            chunks.append(txt)
    return "\n".join(chunks)


def _ocr_pdf_bytes(raw: bytes, max_pages: int = 5) -> str:
    """OCR fallback for scanned PDFs using pypdfium2 + pytesseract when available."""
    import shutil
    import tempfile

    if shutil.which("tesseract") is None:
        logger.info("Skipping PDF OCR fallback: tesseract binary not found")
        return ""

    try:
        import pypdfium2 as pdfium
        import pytesseract
    except Exception:
        logger.info("Skipping PDF OCR fallback: OCR python dependencies are missing")
        return ""

    text_chunks = []
    with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
        tmp.write(raw)
        tmp.flush()
        pdf = pdfium.PdfDocument(tmp.name)
        page_count = min(len(pdf), max_pages)
        for page_index in range(page_count):
            page = pdf[page_index]
            bitmap = page.render(scale=2.0)
            pil_image = bitmap.to_pil()
            text = (pytesseract.image_to_string(pil_image, lang="spa+eng") or "").strip()
            if text:
                text_chunks.append(text)
            pil_image.close()
            bitmap.close()
            page.close()
        pdf.close()
    return "\n".join(text_chunks)


def _ocr_image_bytes(raw: bytes) -> str:
    """OCR helper for common image formats."""
    import io
    import shutil

    if shutil.which("tesseract") is None:
        return ""

    try:
        from PIL import Image
        import pytesseract
    except Exception:
        return ""

    image = Image.open(io.BytesIO(raw))
    try:
        return (pytesseract.image_to_string(image, lang="spa+eng") or "").strip()
    finally:
        image.close()

def _texto_de_pdf(raw: bytes, file_name: str) -> Optional[str]:
    """Texto de un PDF, por tres caminos en orden de fiabilidad.

    Primero la capa de texto; si sale demasiado corta —60 caracteres— casi
    seguro que es un escaneo, y se pasa a OCR. Si el OCR tampoco da nada, se
    describe visualmente la primera página: peor que el texto, pero mejor que
    nada para un resumen.
    """
    try:
        texto = _normalize_extracted_text(_extract_text_from_pdf(raw, max_pages=10))
        if len(texto) >= 60:
            return texto

        ocr = _normalize_extracted_text(_ocr_pdf_bytes(raw, max_pages=5))
        if ocr:
            logger.info("PDF OCR fallback used for document file=%s", file_name)
            return ocr

        visual = _visual_summary_from_pdf_first_page(raw, file_name=file_name)
        if visual:
            logger.info("PDF visual-analysis fallback used for document file=%s", file_name)
            return visual
    except Exception:
        logger.warning("Failed to extract text from PDF for AI summary", exc_info=True)
    return None


def _texto_de_imagen(raw: bytes, file_name: str) -> Optional[str]:
    """Texto de una imagen: OCR y, si no basta, descripción visual."""
    try:
        ocr = _normalize_extracted_text(_ocr_image_bytes(raw))
        if len(ocr) >= 40:
            logger.info("Image OCR used for document file=%s", file_name)
            return ocr

        visual = _visual_summary_from_image_bytes(raw, file_name=file_name)
        if not visual:
            return None
        logger.info("Image visual-analysis fallback used for document file=%s", file_name)
        if ocr:
            # El OCR corto se conserva como pista: puede llevar el número de
            # factura o el nombre del cliente aunque no sea texto completo.
            return f"{visual}\nTexto detectado parcialmente (OCR): {ocr[:400]}"
        return visual
    except Exception:
        logger.warning("Failed to OCR image for AI summary", exc_info=True)
    return None


#: Extensiones que se tratan como imagen aunque el MIME no lo diga.
_EXTENSIONES_DE_IMAGEN = (".png", ".jpg", ".jpeg", ".tiff", ".tif", ".webp")

#: Extensiones que se tratan como texto plano aunque el MIME no lo diga.
_EXTENSIONES_DE_TEXTO = (".md", ".txt", ".csv")


def extract_document_text(file_key: str, file_name: str, file_mime_type: str) -> Optional[str]:
    """Intenta sacar texto de un fichero guardado, para resumirlo con IA.

    Devuelve `None` cuando no hay nada aprovechable, y **nunca levanta**: un
    fichero del que no se puede extraer texto no es un error del documento, es
    un documento sin resumen.
    """
    try:
        raw = file_storage.get_file_bytes(file_key)
    except Exception:
        logger.warning("Failed to read document file content for AI summary", exc_info=True)
        return None

    mime = file_mime_type or ""
    nombre = (file_name or "").lower()

    if "text" in mime or nombre.endswith(_EXTENSIONES_DE_TEXTO):
        return _normalize_extracted_text(raw.decode("utf-8", errors="ignore")) or None
    if "pdf" in mime:
        return _texto_de_pdf(raw, file_name)
    if mime.startswith("image/") or nombre.endswith(_EXTENSIONES_DE_IMAGEN):
        return _texto_de_imagen(raw, file_name)
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
        logger.exception("Failed to commit new document version for doc=%s", doc_id)
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


def resolve_file_access_token(token: str, file_key: str) -> bool:
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        return False
    if not payload.get("document_file_access"):
        return False
    return payload.get("file_key") == file_key


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
