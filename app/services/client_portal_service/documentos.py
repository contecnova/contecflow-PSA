"""Documentos del portal y su firma.

Parte de `app.services.client_portal_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from app.models.client_portal import ClientDocument
from app.models.project import Project as ProjectModel

from app.services.client_portal_service.serializacion import doc_out
from app.services.client_portal_service.autenticacion import logger


# ── Documents ─────────────────────────────────────────────────────────────────

def get_client_documents(project_id: Optional[str], current_client, db: Session) -> list:

    accessible = current_client.get_project_ids()
    if project_id:
        if accessible and project_id not in accessible:
            raise ValueError("No tienes acceso a ese proyecto")
        q = db.query(ClientDocument).filter(ClientDocument.project_id == project_id)
    elif accessible:
        q = db.query(ClientDocument).filter(ClientDocument.project_id.in_(accessible))
    else:
        q = db.query(ClientDocument).filter(ClientDocument.project_id == None)
    docs = q.filter(ClientDocument.is_visible_to_client == True).order_by(ClientDocument.created_at.desc()).all()
    return [doc_out(d) for d in docs]


def get_all_documents(project_id: str, db: Session) -> list:

    docs = db.query(ClientDocument).filter(
        ClientDocument.project_id == project_id
    ).order_by(ClientDocument.created_at.desc()).all()
    return [doc_out(d) for d in docs]


def upload_document(payload, project_id: str, current_user, db: Session) -> dict:

    doc = ClientDocument(project_id=project_id, uploaded_by=current_user.id, **payload.model_dump())
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc_out(doc)


def _load_signable_document(doc_id: str, current_client, db: Session):
    _acc = current_client.get_project_ids()
    if not _acc:
        raise ValueError("No hay proyectos asignados a este cliente")
    doc = db.query(ClientDocument).filter(
        ClientDocument.id == doc_id,
        ClientDocument.project_id.in_(_acc)
    ).first()
    if not doc:
        raise ValueError("Documento no encontrado")
    if doc.signed_by_client:
        raise ValueError("El documento ya fue firmado")
    return doc


def _apply_signature_metadata(doc, signer_name: str, signer_job_title: Optional[str], ip: str, now: datetime) -> None:
    doc.signed_by_client    = True
    doc.signed_at           = now
    doc.signed_by_name      = signer_name
    doc.signed_by_job_title = signer_job_title
    doc.signature_ip        = ip


def _resolve_doc_project_name(doc, db: Session) -> str:
    try:
        proj = db.query(ProjectModel).filter(ProjectModel.id == doc.project_id).first()
        if proj:
            return proj.name
    except Exception:
        logger.warning("Failed to resolve project name for portal doc=%s", getattr(doc, "id", None), exc_info=True)
    return "—"


def _generate_and_store_signature_pdf(
    doc, doc_id: str, signer_name: str, signer_email: str, signer_job_title: Optional[str],
    ip: str, signature_pdf_path_root: str, project_name: str, now: datetime,
    paleta=None,
) -> Optional[str]:
    """Generate the signature PDF, persist it on disk, set doc.signed_pdf_path,
    and return the base64-encoded PDF bytes. Logs (and swallows) generation
    errors but propagates ValueError for explicit invalid-path conditions."""
    try:
        from app.services.signature_pdf import generate_signed_pdf
        from pathlib import Path
        import base64

        pdf_bytes = generate_signed_pdf(
            document_title=doc.title,
            document_description=doc.description or "",
            signer_name=signer_name,
            signer_email=signer_email,
            signer_job_title=signer_job_title or "",
            project_name=project_name,
            signed_at=now,
            signature_ip=ip,
            original_file_name=doc.file_name or "",
            paleta=paleta,
        )
        pdf_dir = Path(signature_pdf_path_root)
        pdf_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = (pdf_dir / f"signed_{doc_id}.pdf").resolve()
        if pdf_dir.resolve() not in pdf_path.parents:
            raise ValueError("Ruta de PDF inválida")
        with open(str(pdf_path), "wb") as f:
            f.write(pdf_bytes)
        doc.signed_pdf_path = str(pdf_path)
        return base64.b64encode(pdf_bytes).decode()
    except ValueError:
        raise
    except Exception as e:
        logger.error(f"Error generating PDF signature: {e}", exc_info=True)
        return None


def sign_document(doc_id: str, signer_name: str, signer_email: str, signer_job_title: Optional[str],
                  ip: str, signature_pdf_path_root: str, current_client, db: Session) -> dict:
    doc = _load_signable_document(doc_id, current_client, db)
    now = datetime.now(timezone.utc)
    _apply_signature_metadata(doc, signer_name, signer_job_title, ip, now)
    project_name = _resolve_doc_project_name(doc, db)
    # La marca del tenant en el certificado de firma: es lo que recibe el
    # cliente al firmar. Auditoria 2026-08, hallazgo 32. Se resuelve aqui, donde
    # hay `db`, y se pasa hecha: el ayudante no necesita dependencia de base.
    from app.services._pdf_marca import PALETA_POR_DEFECTO, marca_de_organizacion
    marca = marca_de_organizacion(
        db, getattr(doc, "organization_id", None), base=PALETA_POR_DEFECTO,
    )
    pdf_b64 = _generate_and_store_signature_pdf(
        doc, doc_id, signer_name, signer_email, signer_job_title,
        ip, signature_pdf_path_root, project_name, now,
        paleta=marca.paleta,
    )
    db.commit()
    return {"ok": True, "signed_at": str(now)[:16], "signer_name": doc.signed_by_name, "pdf_b64": pdf_b64}


def download_signed_pdf(doc_id: str, current_client, db: Session) -> bytes:
    import os

    _acc = current_client.get_project_ids()
    if not _acc:
        raise ValueError("No hay proyectos asignados a este cliente")
    doc = db.query(ClientDocument).filter(
        ClientDocument.id == doc_id,
        ClientDocument.project_id.in_(_acc),
        ClientDocument.signed_by_client == True
    ).first()
    if not doc:
        raise ValueError("Documento no encontrado")
    if not doc.signed_pdf_path:
        raise ValueError("PDF de firma no disponible")
    if not os.path.exists(doc.signed_pdf_path):
        raise ValueError("Archivo de firma no encontrado en el servidor")
    with open(doc.signed_pdf_path, "rb") as f:
        return f.read(), doc.title
