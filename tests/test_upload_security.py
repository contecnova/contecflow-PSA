"""Seguridad de subida de ficheros unificada (auditoría 2026-08, P1-8).

Antes había cuatro comportamientos distintos entre los seis endpoints con
`UploadFile`, y el más permisivo no validaba nada:

  - documents.py           → extensión + MIME + bytes mágicos (el bueno)
  - expenses.py            → sólo el Content-Type que declara el CLIENTE
  - ai_modules.py          → sólo que el nombre acabe en .pdf
  - billing_reports.py     → nada de tipo; tope de 5 MB dentro del servicio
  - collaboration/files.py → NADA, con tope propio de 500 MB comprobado después
                             de leerlo todo en memoria; y una segunda vía (subir
                             versión nueva) sin ningún tope

Ahora todos pasan por `app/core/uploads.py`, y aquí se fija ese contrato.
"""
from __future__ import annotations

import io

import pytest
from fastapi import HTTPException, UploadFile

from app.core.uploads import (
    UploadProfile,
    detect_mime_from_magic,
    max_bytes_for,
    read_upload_within_limit_sync,
    safe_filename,
    validate_upload,
)

PDF = b"%PDF-1.7\n" + b"a" * 512
PNG = b"\x89PNG\r\n\x1a\n" + b"b" * 512
ELF = b"\x7fELF" + b"c" * 512
EXE = b"MZ" + b"d" * 512
ZIP = b"PK\x03\x04" + b"e" * 512


def _upload(name: str, content_type: str, data: bytes) -> UploadFile:
    return UploadFile(filename=name, file=io.BytesIO(data), headers={"content-type": content_type})


# ── El Content-Type del cliente no basta ──────────────────────────────────────

def test_ejecutable_disfrazado_de_imagen_es_rechazado():
    """El caso concreto que expenses.py no detectaba.

    Un ELF con nombre .png y Content-Type image/png pasaba la comprobación
    anterior, que sólo miraba la cabecera declarada por el cliente.
    """
    with pytest.raises(HTTPException) as exc:
        validate_upload("factura.png", "image/png", ELF, UploadProfile.RECEIPT)
    assert exc.value.status_code == 415


def test_ejecutable_windows_disfrazado_es_rechazado():
    with pytest.raises(HTTPException) as exc:
        validate_upload("recibo.pdf", "application/pdf", EXE, UploadProfile.RECEIPT)
    assert exc.value.status_code == 415


def test_tipo_real_distinto_del_declarado_es_rechazado():
    """Un PNG real declarado como PDF: incoherencia detectada por bytes mágicos."""
    with pytest.raises(HTTPException) as exc:
        validate_upload("doc.pdf", "application/pdf", PNG, UploadProfile.DOCUMENT)
    assert exc.value.status_code == 415


def test_zip_bloqueado_aunque_la_extension_mienta():
    with pytest.raises(HTTPException):
        validate_upload("informe.pdf", "application/pdf", ZIP, UploadProfile.DOCUMENT)


def test_extension_de_archivo_comprimido_bloqueada():
    with pytest.raises(HTTPException) as exc:
        validate_upload("backup.zip", "application/zip", b"", UploadProfile.DOCUMENT)
    assert exc.value.status_code == 415


# ── Perfiles ──────────────────────────────────────────────────────────────────

def test_perfil_pdf_only_rechaza_una_imagen_valida():
    """Antes ai_modules sólo miraba el sufijo del nombre."""
    with pytest.raises(HTTPException):
        validate_upload("contrato.png", "image/png", PNG, UploadProfile.PDF_ONLY)


def test_perfil_pdf_only_acepta_un_pdf_real():
    validate_upload("contrato.pdf", "application/pdf", PDF, UploadProfile.PDF_ONLY)


def test_perfil_receipt_acepta_imagen_y_pdf():
    validate_upload("ticket.png", "image/png", PNG, UploadProfile.RECEIPT)
    validate_upload("ticket.pdf", "application/pdf", PDF, UploadProfile.RECEIPT)


def test_perfil_csv_rechaza_un_pdf():
    with pytest.raises(HTTPException):
        validate_upload("datos.pdf", "application/pdf", PDF, UploadProfile.CSV_IMPORT)


# ── Topes de tamaño ───────────────────────────────────────────────────────────

def test_los_topes_por_perfil_son_los_esperados():
    assert max_bytes_for(UploadProfile.RECEIPT) == 10 * 1024 * 1024
    assert max_bytes_for(UploadProfile.PDF_ONLY) == 10 * 1024 * 1024
    assert max_bytes_for(UploadProfile.CSV_IMPORT) == 5 * 1024 * 1024


def test_el_tope_global_sale_de_settings_no_de_una_constante_local():
    """collaboration/files.py tenía un 500 MB propio ignorando este ajuste."""
    from app.core.config import settings

    esperado = int(settings.MAX_FILE_SIZE_MB) * 1024 * 1024
    assert max_bytes_for(UploadProfile.ATTACHMENT) == esperado
    assert max_bytes_for(UploadProfile.DOCUMENT) == esperado
    assert esperado < 500 * 1024 * 1024, "el tope de adjuntos ya no debe ser de 500 MB"


def test_pasarse_del_tope_lanza_413():
    grande = _upload("x.png", "image/png", PNG + b"z" * (2 * 1024 * 1024))
    with pytest.raises(HTTPException) as exc:
        read_upload_within_limit_sync(grande, 1024 * 1024)
    assert exc.value.status_code == 413


def test_la_lectura_no_bufferiza_mas_alla_del_tope():
    """Corta al superar el límite, no después de tenerlo todo en memoria.

    Es la diferencia con el patrón anterior (`data = await file.read()` y luego
    `len(data) > MAX`), que para rechazar 499 MB necesitaba 499 MB de memoria.
    """
    tope = 256 * 1024
    payload = PNG + b"z" * (4 * 1024 * 1024)
    consumido = {"bytes": 0}

    class _Contador(io.BytesIO):
        def read(self, n=-1):  # noqa: D102
            data = super().read(n)
            consumido["bytes"] += len(data)
            return data

    subida = UploadFile(
        filename="x.png", file=_Contador(payload), headers={"content-type": "image/png"}
    )
    with pytest.raises(HTTPException):
        read_upload_within_limit_sync(subida, tope)

    # Se permite el tope más un trozo de lectura (1 MB), no el payload entero.
    assert consumido["bytes"] <= tope + 1024 * 1024 + 1024
    assert consumido["bytes"] < len(payload)


def test_dentro_del_tope_devuelve_el_contenido():
    subida = _upload("x.png", "image/png", PNG)
    assert read_upload_within_limit_sync(subida, 1024 * 1024) == PNG


# ── Nombres de fichero ────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "entrada,esperado_no_contiene",
    [
        ("../../etc/passwd", ".."),
        ("..\\..\\windows\\system32\\cfg", ".."),
        ("/absoluto/ruta.pdf", "/"),
    ],
)
def test_safe_filename_elimina_componentes_de_ruta(entrada, esperado_no_contiene):
    salida = safe_filename(entrada)
    assert esperado_no_contiene not in salida or salida == "archivo"
    assert "/" not in salida and "\\" not in salida


def test_safe_filename_tiene_fallback():
    assert safe_filename("") == "archivo"
    assert safe_filename(None) == "archivo"
    assert safe_filename("...") == "archivo"


# ── Detección por bytes mágicos ───────────────────────────────────────────────

@pytest.mark.parametrize(
    "data,esperado",
    [(PDF, "application/pdf"), (PNG, "image/png"), (ZIP, "application/zip"), (b"", None)],
)
def test_deteccion_por_bytes_magicos(data, esperado):
    assert detect_mime_from_magic(data) == esperado


# ── Compatibilidad del re-export ──────────────────────────────────────────────

def test_documents_service_sigue_re_exportando_el_validador():
    """Los llamadores y tests que lo importaban de allí no deben romperse."""
    from app.services import documents_service
    from app.core import uploads

    assert documents_service.validate_upload is uploads.validate_upload
    assert documents_service.detect_mime_from_magic is uploads.detect_mime_from_magic
