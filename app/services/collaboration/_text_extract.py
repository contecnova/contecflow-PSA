"""Extracción de texto de adjuntos para indexación full-text.

Si pdfminer está disponible se usa para PDF.
Si python-docx está disponible se usa para .docx.
Si openpyxl está disponible se usa para .xlsx.
Fallback: nada (silencio).

Devuelve un texto truncado a `max_chars` para almacenar en
CollaborationAttachment.preview_key (reutilizamos campo) o como columna
nueva — aquí simplemente se usa como input al search engine.
"""
from __future__ import annotations

import io
import logging
import os
import shutil
import subprocess
import tempfile

logger = logging.getLogger(__name__)


def extract_text(data: bytes, filename: str, mime_type: str | None = None, max_chars: int = 200_000) -> str:
    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()

    # Plain text / HTML / JSON / CSV / etc.
    if ext in {"txt", "md", "html", "htm", "json", "csv", "tsv", "xml", "yaml", "yml", "log"}:
        try:
            return data[:max_chars * 2].decode("utf-8", errors="ignore")[:max_chars]
        except Exception:
            return ""

    if ext == "pdf":
        return _from_pdf(data)[:max_chars]
    if ext in {"docx"}:
        return _from_docx(data)[:max_chars]
    if ext in {"xlsx"}:
        return _from_xlsx(data)[:max_chars]
    if ext in {"odt", "rtf", "doc", "ppt", "pptx", "xls", "ods", "odp"}:
        return _from_office_via_libreoffice(data, ext)[:max_chars]

    return ""


def _from_pdf(data: bytes) -> str:
    try:
        from pdfminer.high_level import extract_text as pdf_extract
        return pdf_extract(io.BytesIO(data)) or ""
    # intentional: best-effort fallback, log noise outweighs diagnostic value
    except Exception:
        pass
    # Fallback: pdftotext binary
    if shutil.which("pdftotext"):
        with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
            f.write(data)
            f.flush()
            try:
                proc = subprocess.run(["pdftotext", "-q", f.name, "-"], capture_output=True, timeout=30)
                return proc.stdout.decode("utf-8", errors="ignore")
            except Exception:
                return ""
    return ""


def _from_docx(data: bytes) -> str:
    try:
        from docx import Document
        doc = Document(io.BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs if p.text)
    except Exception:
        return ""


def _from_xlsx(data: bytes) -> str:
    try:
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        out = []
        for sheet in wb.worksheets:
            for row in sheet.iter_rows(values_only=True):
                out.append(" ".join(str(c) for c in row if c is not None))
        return "\n".join(out)
    except Exception:
        return ""


def _from_office_via_libreoffice(data: bytes, ext: str) -> str:
    bin_path = shutil.which("soffice") or shutil.which("libreoffice")
    if not bin_path:
        return ""
    with tempfile.TemporaryDirectory() as td:
        in_path = os.path.join(td, f"input.{ext}")
        with open(in_path, "wb") as f:
            f.write(data)
        try:
            subprocess.run(
                [bin_path, "--headless", "--convert-to", "txt", "--outdir", td, in_path],
                check=True, capture_output=True, timeout=60,
            )
            txt_path = os.path.join(td, "input.txt")
            if os.path.exists(txt_path):
                with open(txt_path, encoding="utf-8", errors="ignore") as f:
                    return f.read()
        except Exception:
            return ""
    return ""
