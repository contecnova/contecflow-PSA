"""Background thumbnail / preview generator for attachments.

Imágenes:        Pillow (siempre disponible)
PDF:             pdf2image (opcional; si no está, omite)
Office (docx,
xlsx, etc):      LibreOffice headless (opcional)

Llamado desde el upload via task_queue. Idempotente.
"""
from __future__ import annotations

import io
import logging
import os
import shutil
import subprocess
import tempfile

from app.services.collaboration._storage import storage

logger = logging.getLogger(__name__)


THUMB_MAX_DIM = 320  # px

IMAGE_EXTS = {"png", "jpg", "jpeg", "gif", "webp", "bmp", "tiff"}
PDF_EXTS = {"pdf"}
OFFICE_EXTS = {"doc", "docx", "ppt", "pptx", "xls", "xlsx", "odt", "ods", "odp", "rtf"}


def _ext(name: str) -> str:
    return (name.rsplit(".", 1)[-1] if "." in name else "").lower()


def _image_thumbnail(data: bytes) -> bytes | None:
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(data))
        img.thumbnail((THUMB_MAX_DIM, THUMB_MAX_DIM))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=82, optimize=True)
        return out.getvalue()
    except Exception as exc:
        logger.warning("image thumbnail failed: %s", exc)
        return None


def _pdf_thumbnail(data: bytes) -> bytes | None:
    try:
        from pdf2image import convert_from_bytes
    except Exception:
        logger.debug("_pdf_thumbnail: excepcion ignorada", exc_info=True)
        return None
    try:
        from pdf2image import convert_from_bytes
        pages = convert_from_bytes(data, first_page=1, last_page=1, size=THUMB_MAX_DIM)
        if not pages:
            return None
        out = io.BytesIO()
        pages[0].save(out, format="JPEG", quality=82, optimize=True)
        return out.getvalue()
    except Exception as exc:
        logger.warning("pdf thumbnail failed: %s", exc)
        return None


def _office_thumbnail(data: bytes, ext: str) -> bytes | None:
    """Convierte vía LibreOffice headless a PDF y luego a thumb."""
    if not shutil.which("soffice") and not shutil.which("libreoffice"):
        return None
    cmd = "soffice" if shutil.which("soffice") else "libreoffice"
    with tempfile.TemporaryDirectory() as td:
        in_path = os.path.join(td, f"input.{ext}")
        with open(in_path, "wb") as f:
            f.write(data)
        try:
            subprocess.run(
                [cmd, "--headless", "--convert-to", "pdf", "--outdir", td, in_path],
                check=True, capture_output=True, timeout=60,
            )
            pdf_path = os.path.join(td, "input.pdf")
            if not os.path.exists(pdf_path):
                return None
            with open(pdf_path, "rb") as f:
                return _pdf_thumbnail(f.read())
        except Exception as exc:
            logger.warning("office thumbnail failed: %s", exc)
            return None


def generate_for_attachment(attachment_id: str) -> None:
    """Background entrypoint."""
    from app.db.session import SessionLocal
    from app.models.collaboration import CollaborationAttachment

    db = SessionLocal()
    try:
        att = db.query(CollaborationAttachment).filter(CollaborationAttachment.id == attachment_id).first()
        if not att:
            return
        if att.is_quarantined:
            att.preview_status = "skipped"
            db.commit()
            return
        att.preview_status = "pending"
        db.commit()
        try:
            data = storage.read(att.storage_key)
        except Exception:
            logger.warning("generate_for_attachment: excepcion ignorada", exc_info=True)
            att.preview_status = "failed"
            db.commit()
            return

        ext = _ext(att.name or "")
        if ext in IMAGE_EXTS:
            thumb = _image_thumbnail(data)
        elif ext in PDF_EXTS:
            thumb = _pdf_thumbnail(data)
        elif ext in OFFICE_EXTS:
            thumb = _office_thumbnail(data, ext)
        else:
            att.preview_status = "skipped"
            db.commit()
            return

        if not thumb:
            att.preview_status = "failed"
            db.commit()
            return

        thumb_key = f"{att.storage_key}.thumb.jpg"
        storage.save_bytes(thumb_key, thumb)
        att.preview_key = thumb_key
        att.preview_status = "ready"
        db.commit()
    finally:
        db.close()
