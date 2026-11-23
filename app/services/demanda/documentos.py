"""Repositorio documental del expediente, etiquetado por fase.

- El fichero va al almacén de siempre (`s3_service.file_storage`) tras validar
  tipo real y tamaño (`app.core.uploads.validate_upload`) y pasar el antivirus.
- Desde que la ficha está bloqueada para el cliente, lo que sube el cliente
  queda como **anexo registrado** (`is_annex`), nunca sustituye nada.
- Nada se borra a mano: el repositorio es la historia del expediente (la
  retención del tipo `demand_requests` lo borra entero al vencer, salvo
  bloqueo legal).
- Lo que sube el equipo es interno por defecto (el cliente no lo ve).
- Cada descarga queda en auditoría (RGPD: `personal_data` lo marca quien sube).
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.services.demanda import definicion as D
from app.services.demanda.acceso import Actor
from app.services.demanda.motor import CERRADOS, ahora, flujo_de


def subir(db: Session, actor: Actor, req, *, nombre: str, content_type: str, contenido: bytes,
          etiqueta: Optional[str] = None, datos_personales: bool = False, interno: Optional[bool] = None,
          ip: Optional[str] = None):
    from app.core.config import settings
    from app.core.uploads import safe_filename, validate_upload
    from app.models.demanda import DemandDocument
    from app.services.audit import audit_log
    from app.services.collaboration._storage import scan_with_av
    from app.services.s3_service import file_storage
    from app.services.settings_service import get_runtime_int
    if req.status in CERRADOS and req.status != "approved":
        raise error(409, "dem_estado_no_permite", estado=req.status)
    maximo = (get_runtime_int(db, "MAX_FILE_SIZE_MB", req.organization_id) or settings.MAX_FILE_SIZE_MB) * 1024 * 1024
    if len(contenido) > maximo:
        raise error(413, "fichero_demasiado_grande", max=maximo // (1024 * 1024))
    validate_upload(nombre or "", content_type or "", contenido)
    av, detalle = scan_with_av(contenido)
    usuario = actor.user if actor.kind == "user" else None
    if av in ("infected", "unavailable"):   # A24: antivirus caído = no se acepta
        audit_log(db, usuario, "UPLOAD_BLOCKED", "demand_request", req.id, nombre, metadata={"antivirus": detalle})
        db.commit()
        raise error(422, "antivirus_bloqueado")
    f = D.fase(flujo_de(req), req.current_phase_key) or {}
    etiqueta = etiqueta if etiqueta in D.ETIQUETAS_DE_DOCUMENTO else (f.get("documents_tag") or "other")
    if actor.kind == "client":
        interno = False
    elif interno is None:
        interno = True
    anexo = actor.kind == "client" and bool(req.client_locked)
    if anexo:
        etiqueta = "annex"
    doc = DemandDocument(organization_id=req.organization_id, request_id=req.id, phase_key=req.current_phase_key,
                         tag=etiqueta, file_name=safe_filename(nombre)[:255], mime=content_type, size=len(contenido),
                         is_annex=anexo, personal_data=bool(datos_personales), internal=bool(interno),
                         uploaded_by_user_id=actor.id if actor.kind == "user" else None,
                         uploaded_by_client_id=actor.id if actor.kind == "client" else None,
                         uploaded_by_name=actor.nombre[:255] or None, created_at=ahora())
    db.add(doc)
    db.flush()
    clave, _tam = file_storage.upload_file(file_content=contenido, file_name=doc.file_name, document_id=doc.id,
                                           version_num=1, content_type=content_type or "application/octet-stream")
    doc.file_key = clave
    audit_log(db, usuario, "UPLOAD", "demand_request", req.id, doc.file_name, ip_address=ip,
              metadata={"document_id": doc.id, "tag": etiqueta, "phase": req.current_phase_key, "annex": anexo,
                        "personal_data": bool(datos_personales), "actor_kind": actor.kind,
                        "client_user_id": actor.id if actor.kind == "client" else None})
    db.commit()
    return doc


def guardar_generado(db: Session, req, actor: Actor, nombre: str, mime: str, contenido: bytes, etiqueta: str):
    """Documento que genera el sistema (Executive Summary): sin validación de subida."""
    from app.models.demanda import DemandDocument
    from app.services.s3_service import file_storage
    doc = DemandDocument(organization_id=req.organization_id, request_id=req.id, phase_key=req.current_phase_key,
                         tag=etiqueta, file_name=nombre[:255], mime=mime, size=len(contenido), internal=True,
                         uploaded_by_user_id=actor.id if actor.kind == "user" else None,
                         uploaded_by_name=actor.nombre[:255] or "Sistema", created_at=ahora())
    db.add(doc)
    db.flush()
    clave, _ = file_storage.upload_file(file_content=contenido, file_name=doc.file_name, document_id=doc.id,
                                        version_num=1, content_type=mime)
    doc.file_key = clave
    return doc


def leer(almacen, clave: str) -> bytes:
    """Bytes del fichero en el almacén local o en S3 (S3Service no tiene `get_file_bytes`)."""
    if hasattr(almacen, "get_file_bytes"):
        return almacen.get_file_bytes(clave)
    respuesta = almacen.client.get_object(Bucket=almacen.bucket, Key=clave)
    return respuesta["Body"].read()


def descargar(db: Session, actor: Actor, req, doc_id: str, ip: Optional[str] = None) -> tuple[bytes, str, str]:
    """(contenido, nombre, mime). Auditado. El cliente solo baja lo no interno."""
    from app.models.demanda import DemandDocument
    from app.services.audit import audit_log
    from app.services.s3_service import file_storage
    doc = db.query(DemandDocument).filter(DemandDocument.id == doc_id, DemandDocument.request_id == req.id).first()
    if doc is None or (actor.kind == "client" and doc.internal) or not doc.file_key:
        raise error(404, "dem_documento_no_encontrado")
    contenido = leer(file_storage, doc.file_key)
    audit_log(db, actor.user if actor.kind == "user" else None, "DOWNLOAD", "demand_request", req.id, doc.file_name,
              ip_address=ip, metadata={"document_id": doc.id, "personal_data": bool(doc.personal_data),
                                       "actor_kind": actor.kind,
                                       "client_user_id": actor.id if actor.kind == "client" else None})
    db.commit()
    return contenido, doc.file_name, doc.mime or "application/octet-stream"
