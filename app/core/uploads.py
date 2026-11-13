"""Seguridad de subida de ficheros — primitiva compartida.

Auditoría 2026-08 (hallazgo P1-8). Antes de este módulo la validación de subidas
vivía dentro de `app/services/documents_service.py`, un servicio de dominio, y
sólo la usaban los dos endpoints de ese dominio. Los otros cuatro endpoints con
`UploadFile` hacían cada uno su propia cosa:

  - expenses.py          → sólo el `Content-Type` que declara el cliente, que es
                           precisamente el dato que un atacante controla.
  - ai_modules.py        → sólo la extensión del nombre de fichero.
  - billing_reports.py   → tamaño en el servicio, sin validar tipo.
  - collaboration/files.py → NADA. Y con un tope propio de 500 MB, comprobado
                           DESPUÉS de `await file.read()`, así que 499 MB
                           acababan en memoria antes de rechazarse. Además
                           ignoraba `settings.MAX_FILE_SIZE_MB` (100), que ya
                           existía.

La validación de subidas es una preocupación transversal de seguridad, no de un
dominio: aquí es donde vive. `documents_service` la re-exporta para no romper a
sus llamadores ni a los tests que la importan de allí.

── Cómo usarlo ───────────────────────────────────────────────────────────────
    from app.core.uploads import UploadProfile, read_and_validate_upload

    content = await read_and_validate_upload(file, UploadProfile.DOCUMENT)

Eso hace, en este orden: leer por trozos abortando en cuanto se pasa del tope
(sin bufferizar el fichero entero), y después validar extensión, MIME declarado,
bytes mágicos y coherencia entre lo declarado y lo real.
"""
from __future__ import annotations

import enum
import os
from typing import Iterable, Optional

from fastapi import UploadFile

from app.core.errores import ErrorDeDominio

from app.core.config import settings

# ── Catálogos ─────────────────────────────────────────────────────────────────

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

_IMAGE_MIME = {"image/jpeg", "image/png", "image/webp", "image/gif", "image/tiff"}
_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".tiff", ".tif"}


class UploadProfile(enum.Enum):
    """Qué se acepta en cada punto de subida.

    Cada endpoint declara su perfil en vez de repetir listas de tipos: así el
    catálogo se amplía en un sitio y ningún endpoint se queda atrás.
    """

    DOCUMENT = "document"          # gestor documental: todo el catálogo aprobado
    RECEIPT = "receipt"            # OCR de gastos: imágenes y PDF
    PDF_ONLY = "pdf_only"          # análisis de contratos
    CSV_IMPORT = "csv_import"      # importación de datos
    ATTACHMENT = "attachment"      # adjuntos de chat: catálogo aprobado


_PROFILE_MIME: dict[UploadProfile, set[str]] = {
    UploadProfile.DOCUMENT: ALLOWED_MIME_TYPES,
    UploadProfile.ATTACHMENT: ALLOWED_MIME_TYPES,
    UploadProfile.RECEIPT: _IMAGE_MIME | {"application/pdf"},
    UploadProfile.PDF_ONLY: {"application/pdf"},
    UploadProfile.CSV_IMPORT: {"text/csv", "text/plain", "application/vnd.ms-excel"},
}

_PROFILE_EXT: dict[UploadProfile, set[str]] = {
    UploadProfile.DOCUMENT: ALLOWED_EXTENSIONS,
    UploadProfile.ATTACHMENT: ALLOWED_EXTENSIONS,
    UploadProfile.RECEIPT: _IMAGE_EXT | {".pdf"},
    UploadProfile.PDF_ONLY: {".pdf"},
    UploadProfile.CSV_IMPORT: {".csv", ".txt"},
}

# Topes por perfil, en MB. El global sale de settings.MAX_FILE_SIZE_MB para que
# se pueda ajustar por despliegue; los perfiles acotan más donde tiene sentido.
_PROFILE_MAX_MB: dict[UploadProfile, int] = {
    UploadProfile.DOCUMENT: 0,      # 0 → usa el global
    UploadProfile.ATTACHMENT: 0,
    UploadProfile.RECEIPT: 10,
    UploadProfile.PDF_ONLY: 10,
    UploadProfile.CSV_IMPORT: 5,
}

_READ_CHUNK = 1024 * 1024  # 1 MB


def max_bytes_for(profile: UploadProfile) -> int:
    mb = _PROFILE_MAX_MB.get(profile, 0) or int(getattr(settings, "MAX_FILE_SIZE_MB", 100))
    return mb * 1024 * 1024


# ── Detección por bytes mágicos ───────────────────────────────────────────────

#: Firma de cabecera → tipo MIME. Auditoría 2026-09 (hallazgo 18): esto era una
#: cascada de nueve `if` con `return`, que es **una tabla escrita como código**.
#: Como tabla se lee de un vistazo y añadir un formato es añadir una fila, no
#: una rama. El orden importa sólo en que la primera que encaje gana, y ninguna
#: de estas firmas es prefijo de otra.
_FIRMAS: tuple[tuple[bytes, str], ...] = (
    (b"%PDF-",                  "application/pdf"),
    (b"\x89PNG\r\n\x1a\n",     "image/png"),
    (b"\xff\xd8\xff",          "image/jpeg"),
    (b"GIF87a",                 "image/gif"),
    (b"GIF89a",                 "image/gif"),
    (b"\x1aE\xdf\xa3",          "video/webm"),
    (b"ID3",                    "audio/mpeg"),
    (b"\xff\xfb",               "audio/mpeg"),
)

#: Lo que se encuentra dentro de un ZIP y qué formato de Office significa. Los
#: `.docx`, `.xlsx`, `.pptx` y `.odt` son todos ZIP: el tipo real está en los
#: nombres de las entradas, no en la cabecera.
_ENTRADAS_DE_ZIP: tuple[tuple[str, str], ...] = (
    ("word/",       "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ("xl/",         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ("ppt/",        "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
    ("content.xml", "application/vnd.oasis.opendocument.text"),
)


def _mime_de_zip(content: bytes) -> str:
    """Qué formato es un ZIP, mirando los nombres de sus primeras entradas.

    Se leen 2 KB en crudo en vez de abrirlo como ZIP a propósito: esto corre
    sobre bytes que aún no se ha decidido aceptar, y un lector de ZIP sobre
    contenido no validado es superficie de ataque (bombas de descompresión,
    rutas con `..`). Buscar subcadenas no ejecuta nada.
    """
    nombres = content[:2048].decode("latin-1", errors="ignore").lower()
    for marca, mime in _ENTRADAS_DE_ZIP:
        if marca in nombres:
            return mime
    return "application/zip"


def detect_mime_from_magic(content: bytes) -> Optional[str]:
    """El tipo real de un archivo según sus primeros bytes, o `None`."""
    if not content:
        return None
    head = content[:16]
    for firma, mime in _FIRMAS:
        if head.startswith(firma):
            return mime
    # Los dos que no son un simple prefijo: WEBP lleva el marcador en el byte 8,
    # y un ZIP hay que abrirlo un poco para saber qué es.
    if head.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "image/webp"
    if head.startswith(b"PK\x03\x04"):
        return _mime_de_zip(content)
    return None


# ── Validación de contenido ───────────────────────────────────────────────────

#: Lo que manda un cliente que no sabe qué tipo es. No es una afirmación, así
#: que no puede contradecir a los bytes mágicos.
_TIPOS_SIN_OPINION = ("application/octet-stream", "binary/octet-stream")


def _comprobar_extension(file_name: str, permitidas: set) -> None:
    """Rechaza por extensión. Los comprimidos van aparte, y con su motivo."""
    ext = os.path.splitext(file_name or "")[1].lower()
    if ext in BLOCKED_ARCHIVE_EXTENSIONS:
        raise ErrorDeDominio(
            415,
            "Subida de archivos comprimidos bloqueada por seguridad "
            "(riesgo de fuga de secretos y payloads ocultos).",
        )
    if ext and ext not in permitidas:
        raise ErrorDeDominio(
            415,
            f"Tipo de archivo no permitido (extensión: {ext}). "
            f"Formatos aceptados aquí: {', '.join(sorted(permitidas))}.",
        )


def _comprobar_ejecutable(content: bytes) -> None:
    """Rechaza lo que empieza como un ejecutable o un script, sea cual sea el nombre."""
    if not content:
        return
    cabecera = content[:8]
    for magic in BLOCKED_MAGIC_BYTES:
        if cabecera.startswith(magic):
            raise ErrorDeDominio(
                415,
                "El contenido del archivo parece ser un ejecutable o script. "
                "Subida rechazada por seguridad.",
            )


def _comprobar_tipo_real(content: bytes, content_type: str, permitidos: set) -> None:
    """El cruce que importa: lo declarado contra lo que los bytes dicen.

    El `Content-Type` lo elige el cliente, así que por sí solo no prueba nada.
    Lo que se comprueba aquí es la **coherencia** entre los dos, y por eso este
    trozo va después de los demás y no antes.

    `application/octet-stream` se acepta como «no lo sé» y no cuenta como
    desacuerdo: es lo que mandan los clientes que no adivinan el tipo.
    """
    detectado = detect_mime_from_magic(content)
    if detectado == "application/zip":
        raise ErrorDeDominio(
            415, "Contenedor ZIP detectado. Este tipo de archivo está bloqueado por seguridad."
        )
    if detectado and detectado not in permitidos:
        raise ErrorDeDominio(415, f"Tipo de archivo detectado no permitido: {detectado}")
    if (
        detectado
        and content_type
        and content_type not in _TIPOS_SIN_OPINION
        and detectado != content_type
    ):
        raise ErrorDeDominio(
            415,
            f"El tipo real del archivo ({detectado}) no coincide con el "
            f"Content-Type enviado ({content_type}).",
        )


def validate_upload(
    file_name: str,
    content_type: str,
    content: bytes,
    profile: UploadProfile = UploadProfile.DOCUMENT,
) -> None:
    """Valida extensión, MIME declarado, bytes mágicos y su coherencia.

    Auditoría 2026-09 (hallazgo 18): eran cuatro comprobaciones independientes
    en una sola función de complejidad 11. Cada una tiene ahora su nombre, y el
    orden —que sí importa: primero lo barato, el cruce caro al final— se lee en
    estas cuatro líneas.
    """
    permitidas = _PROFILE_EXT.get(profile, ALLOWED_EXTENSIONS)
    permitidos = _PROFILE_MIME.get(profile, ALLOWED_MIME_TYPES)

    _comprobar_extension(file_name, permitidas)
    # Auditoria 2026-11: sin extension no habia lista que aplicar y el fichero
    # pasaba (un .html o .svg renombrado a `informe`). Sin extension, solo si
    # los bytes dicen que es un tipo permitido.
    if not os.path.splitext(file_name or "")[1] and detect_mime_from_magic(content) not in permitidos:
        raise ErrorDeDominio(415, "Archivo sin extensión y de tipo no reconocido: añade la extensión.")
    if content_type and content_type not in permitidos and content_type not in _TIPOS_SIN_OPINION:
        raise ErrorDeDominio(415, f"Tipo de contenido no permitido: {content_type}.")
    _comprobar_ejecutable(content)
    _comprobar_tipo_real(content, content_type, permitidos)


# ── Lectura acotada ──────────────────────────────────────────────────────────

async def read_upload_within_limit(file: UploadFile, max_bytes: int) -> bytes:
    """Lee el fichero por trozos y aborta en cuanto se pasa del tope.

    Antes el patrón era `data = await file.read()` y comprobar `len(data)`
    después: para rechazar una subida de 499 MB había que haberla metido entera
    en memoria primero. Aquí se corta al superar el límite, así que como mucho se
    retiene el tope más un trozo.
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_READ_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise ErrorDeDominio(
                413,
                f"El archivo supera el tamaño máximo permitido "
                f"({max_bytes // (1024 * 1024)} MB).",
            )
        chunks.append(chunk)
    return b"".join(chunks)


async def read_and_validate_upload(
    file: UploadFile,
    profile: UploadProfile = UploadProfile.DOCUMENT,
) -> bytes:
    """Punto único de entrada: lee con tope y valida el contenido.

    Devuelve los bytes ya validados. Lanza 413 si excede el tamaño y 415 si el
    tipo no está permitido o el contenido no concuerda con lo declarado.
    """
    content = await read_upload_within_limit(file, max_bytes_for(profile))
    validate_upload(file.filename or "", file.content_type or "", content, profile)
    return content


def read_upload_within_limit_sync(file: UploadFile, max_bytes: int) -> bytes:
    """Variante sincrónica de `read_upload_within_limit`.

    Para endpoints declarados con `def` y no `async def`. No se convierten a
    async a propósito: su cuerpo hace trabajo bloqueante (extraer texto de un
    PDF, parsear un CSV) y en una corutina eso congelaría el event loop para
    todos los usuarios. FastAPI ya los ejecuta en un threadpool.
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = file.file.read(_READ_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise ErrorDeDominio(
                413,
                f"El archivo supera el tamaño máximo permitido "
                f"({max_bytes // (1024 * 1024)} MB).",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def read_and_validate_upload_sync(
    file: UploadFile,
    profile: UploadProfile = UploadProfile.DOCUMENT,
) -> bytes:
    """Igual que `read_and_validate_upload`, para endpoints sincrónicos."""
    content = read_upload_within_limit_sync(file, max_bytes_for(profile))
    validate_upload(file.filename or "", file.content_type or "", content, profile)
    return content


def safe_filename(name: Optional[str], *, fallback: str = "archivo") -> str:
    """Nombre de fichero sin componentes de ruta ni caracteres de control.

    Evita que un `filename` con `../` o separadores escape del directorio de
    destino cuando se usa para construir una ruta.
    """
    raw = (name or "").strip()
    raw = raw.replace("\\", "/").split("/")[-1]
    cleaned = "".join(ch for ch in raw if ch.isprintable() and ch not in '<>:"|?*')
    cleaned = cleaned.lstrip(".")
    return cleaned or fallback


__all__: Iterable[str] = (
    "ALLOWED_EXTENSIONS",
    "ALLOWED_MIME_TYPES",
    "BLOCKED_ARCHIVE_EXTENSIONS",
    "BLOCKED_MAGIC_BYTES",
    "UploadProfile",
    "detect_mime_from_magic",
    "max_bytes_for",
    "read_and_validate_upload",
    "read_and_validate_upload_sync",
    "read_upload_within_limit",
    "read_upload_within_limit_sync",
    "safe_filename",
    "validate_upload",
)
