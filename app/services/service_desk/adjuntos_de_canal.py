"""Adjuntos de los canales del service desk (WhatsApp, Slack) (17-11-2026).

Lo que llega por un canal se guarda como documento del ticket, igual que los
adjuntos del correo entrante, con estas comprobaciones en este orden:

1. **Tamaño**: `SD_CHANNEL_MAX_ATTACHMENT_MB` de la empresa (la descarga ya se
   corta al pasarlo: no se retiene mas que el tope).
2. **Tipo**: extension, MIME declarado, bytes magicos y su coherencia con el
   perfil `UploadProfile.CHANNEL` (sin SVG ni ejecutables ni comprimidos).
3. **Antivirus**: `collaboration._storage.scan_with_av` (clamd si
   `CLAMAV_ENABLED`; si no, la firma EICAR). Infectado: no se guarda y queda
   en la auditoria (`UPLOAD_BLOCKED`).

Lo que no pasa se rechaza con su motivo (`size`, `type`, `virus`, `owner`) y el
mensaje del canal lo anota para que el agente sepa que hubo un adjunto.

Tambien lee un documento del ticket para enviarlo por el canal (`leer`).
"""
from __future__ import annotations

import logging
import mimetypes
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.core.errores import ErrorDeDominio

logger = logging.getLogger(__name__)

#: Tope por defecto (MB) si la empresa no fija `SD_CHANNEL_MAX_ATTACHMENT_MB`.
TOPE_POR_DEFECTO_MB = 16
#: Extension por tipo, para los ficheros que llegan sin nombre (fotos y notas de voz).
_EXTENSIONES = {
    "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif",
    "audio/ogg": ".ogg", "audio/opus": ".opus", "audio/aac": ".aac", "audio/amr": ".amr", "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a", "video/mp4": ".mp4", "video/3gpp": ".3gp", "video/quicktime": ".mov",
    "application/pdf": ".pdf", "text/plain": ".txt",
}


@dataclass
class Resultado:
    document_id: Optional[str] = None
    nombre: Optional[str] = None
    motivo: Optional[str] = None      # size | type | virus | owner | download


def tope_en_bytes(db: Session, org_id) -> int:
    from app.services.settings_service import get_runtime_int
    mb = get_runtime_int(db, "SD_CHANNEL_MAX_ATTACHMENT_MB", org_id) or TOPE_POR_DEFECTO_MB
    return max(1, int(mb)) * 1024 * 1024


def nombre_de_fichero(nombre: Optional[str], tipo: Optional[str], respaldo: str) -> str:
    """Nombre seguro y con extension (las fotos y audios de WhatsApp no traen nombre)."""
    from app.core.uploads import safe_filename
    limpio = safe_filename(nombre, fallback=respaldo)
    if "." not in limpio:
        base = (tipo or "").split(";")[0].strip().lower()
        limpio += _EXTENSIONES.get(base) or mimetypes.guess_extension(base) or ""
    return limpio[:200]


def _dueño(db: Session, ticket) -> Optional[str]:
    """El documento necesita un usuario dueño de la empresa (como el correo entrante)."""
    from app.models.user import User, UserRole
    dueño = ticket.assigned_to_user_id or ticket.created_by_user_id
    if dueño:
        return dueño
    admin = db.query(User.id).filter(User.role == UserRole.admin, User.is_active == True,  # noqa: E712
                                     User.organization_id == ticket.organization_id).first()
    return admin[0] if admin else None


def guardar(db: Session, ticket, *, nombre: str, tipo: Optional[str], contenido: bytes, origen: str,
            descripcion: Optional[str] = None) -> Resultado:
    """Valida, escanea y guarda `contenido` como documento del ticket. No confirma."""
    from app.core.uploads import UploadProfile, validate_upload
    from app.models.documents import Document, DocumentCategory, DocumentVersion
    from app.services.audit import audit_log
    from app.services.collaboration._storage import scan_with_av
    from app.services.s3_service import file_storage

    tipo = (tipo or "application/octet-stream").split(";")[0].strip().lower()
    if len(contenido) > tope_en_bytes(db, ticket.organization_id):
        return Resultado(nombre=nombre, motivo="size")
    try:
        validate_upload(nombre, tipo, contenido, UploadProfile.CHANNEL)
    except ErrorDeDominio as e:
        logger.info("adjunto de %s rechazado (%s): %s", origen, nombre, e)
        return Resultado(nombre=nombre, motivo="type")
    estado_av, detalle = scan_with_av(contenido)
    if estado_av == "infected":
        audit_log(db, None, "UPLOAD_BLOCKED", "ticket_attachment", ticket.id, nombre,
                  metadata={"channel": origen, "antivirus": detalle, "organization_id": ticket.organization_id})
        return Resultado(nombre=nombre, motivo="virus")
    dueño = _dueño(db, ticket)
    if dueño is None:
        return Resultado(nombre=nombre, motivo="owner")
    doc = Document(title=nombre[:255], description=(descripcion or f"Adjunto recibido por {origen}")[:1000],
                   category=DocumentCategory.other, ticket_id=ticket.id,
                   organization_id=ticket.organization_id, created_by=dueño)
    db.add(doc)
    db.flush()
    clave, tamaño = file_storage.upload_file(file_content=contenido, file_name=nombre, document_id=doc.id,
                                             version_num=1, content_type=tipo)
    db.add(DocumentVersion(document_id=doc.id, version_num=1, file_key=clave, file_name=nombre[:255],
                           file_size=tamaño, file_mime_type=tipo, change_note=f"Canal {origen}",
                           created_by=dueño, organization_id=ticket.organization_id))
    audit_log(db, None, "CREATE", "ticket_attachment", doc.id, nombre,
              metadata={"channel": origen, "ticket_id": ticket.id, "size": tamaño, "antivirus": estado_av,
                        "organization_id": ticket.organization_id})
    return Resultado(document_id=doc.id, nombre=nombre)


@dataclass
class Fichero:
    nombre: str
    tipo: str
    contenido: bytes


def documento_del_ticket(db: Session, ticket, document_id: str):
    """El documento (y su ultima version) del ticket; 404 si no es de ese ticket."""
    from app.core.codigos_de_error import error as error_con_codigo
    from app.models.documents import Document, DocumentVersion
    doc = db.query(Document).filter(Document.id == document_id, Document.ticket_id == ticket.id,
                                    Document.organization_id == ticket.organization_id).first()
    if doc is None:
        raise error_con_codigo(404, "adjunto_no_encontrado")
    version = (db.query(DocumentVersion).filter(DocumentVersion.document_id == doc.id)
               .order_by(DocumentVersion.version_num.desc()).first())
    if version is None:
        raise error_con_codigo(404, "adjunto_no_encontrado")
    return doc, version


def leer(db: Session, ticket, document_id: str) -> Fichero:
    """Los bytes de un documento del ticket, para enviarlo por el canal."""
    from app.services.s3_service import file_storage
    _doc, version = documento_del_ticket(db, ticket, document_id)
    lector = getattr(file_storage, "get_file_bytes", None)
    if lector is not None:
        contenido = lector(version.file_key)
    else:  # S3
        contenido = file_storage.client.get_object(Bucket=file_storage.bucket, Key=version.file_key)["Body"].read()
    return Fichero(nombre=version.file_name, tipo=version.file_mime_type or "application/octet-stream",
                   contenido=contenido)


def listar(db: Session, ticket) -> list[dict]:
    """Documentos del ticket (los que se pueden enviar por el canal)."""
    if ticket is None:
        return []
    from app.models.documents import Document, DocumentVersion
    filas = (db.query(Document).filter(Document.ticket_id == ticket.id,
                                       Document.organization_id == ticket.organization_id,
                                       Document.is_archived.isnot(True))
             .order_by(Document.created_at.desc()).limit(50).all())
    salida = []
    for d in filas:
        v = (db.query(DocumentVersion).filter(DocumentVersion.document_id == d.id)
             .order_by(DocumentVersion.version_num.desc()).first())
        salida.append({"id": d.id, "title": d.title, "file_name": v.file_name if v else d.title,
                       "mime_type": v.file_mime_type if v else None, "size": v.file_size if v else None})
    return salida


def descargar_acotado(cliente, url: str, *, headers: dict, tope: int, timeout: float) -> tuple[bytes, Optional[str]]:
    """GET por trozos que se corta al pasar `tope`. Devuelve (bytes, content-type).

    Lanza `ErrorDeDominio(413)` si se pasa; los errores de red, tal cual.
    """
    partes, total = [], 0
    with cliente.stream("GET", url, headers=headers, timeout=timeout) as r:
        r.raise_for_status()
        largo = r.headers.get("content-length")
        if largo and largo.isdigit() and int(largo) > tope:
            raise ErrorDeDominio(413, "adjunto demasiado grande")
        for trozo in r.iter_bytes():
            total += len(trozo)
            if total > tope:
                raise ErrorDeDominio(413, "adjunto demasiado grande")
            partes.append(trozo)
        return b"".join(partes), r.headers.get("content-type")
