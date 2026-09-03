"""Instantaneas de documentos en edicion colaborativa.

Auditoria 2026-08 (hallazgo 22). Este codigo vivia en `v238_service.py`, un
fichero de 784 lineas nombrado por NUMERO DE VERSION y con SEIS dominios sin
relacion dentro: etapas del embudo, planificacion de capacidad, analitica
ad-hoc, pagos, instantaneas de colaboracion y SCIM.

Agrupar por version en lugar de por dominio tiene un coste concreto: nadie sabe
donde buscar, y un fichero con seis dominios no tiene revisor natural — quien
entra a tocar los pagos no revisa la analitica que hay 300 lineas mas abajo. Fue
esa misma mala ubicacion la que oculto el P0 numero 1 de la auditoria, escondido
en un fichero llamado `mfa_service`.

El reparto se pudo hacer mecanicamente porque los seis dominios nunca estuvieron
acoplados, solo apilados: se comprobo por AST que no habia ni una llamada entre
grupos ni un solo ciclo. Los cuerpos se movieron verbatim.
"""

from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models.document_collab import DocumentCollabSnapshot
from app.models.documents import Document


def save_collab_snapshot_record(document_id: str, body: bytes, user_id: str, db: Session) -> dict:
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if not body:
        raise HTTPException(status_code=400, detail="Request body must be the Yjs binary state vector")

    db.query(DocumentCollabSnapshot).filter(
        DocumentCollabSnapshot.document_id == document_id,
        DocumentCollabSnapshot.is_current == True,
    ).update({"is_current": False})

    last = db.query(DocumentCollabSnapshot).filter(
        DocumentCollabSnapshot.document_id == document_id,
    ).order_by(DocumentCollabSnapshot.clock.desc()).first()
    clock = (last.clock or 0) + 1 if last else 1

    snapshot = DocumentCollabSnapshot(
        document_id=document_id,
        state_vector=body,
        clock=clock,
        size_bytes=len(body),
        is_current=True,
        created_by=user_id,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return {
        "id": snapshot.id,
        "document_id": document_id,
        "clock": snapshot.clock,
        "size_bytes": snapshot.size_bytes,
        "created_at": str(snapshot.created_at),
    }


def load_collab_snapshot_record(document_id: str, db: Session) -> dict:
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    snapshot = db.query(DocumentCollabSnapshot).filter(
        DocumentCollabSnapshot.document_id == document_id,
        DocumentCollabSnapshot.is_current == True,
    ).order_by(DocumentCollabSnapshot.clock.desc()).first()

    if not snapshot:
        return {"document_id": document_id, "snapshot": None, "clock": 0}

    import base64
    return {
        "document_id": document_id,
        "id": snapshot.id,
        "clock": snapshot.clock,
        "size_bytes": snapshot.size_bytes,
        "state_vector_b64": base64.b64encode(snapshot.state_vector).decode("utf-8"),
        "created_at": str(snapshot.created_at),
    }


def list_collab_snapshots_records(document_id: str, limit: int, db: Session) -> list:
    snapshots = db.query(DocumentCollabSnapshot).filter(
        DocumentCollabSnapshot.document_id == document_id,
    ).order_by(DocumentCollabSnapshot.clock.desc()).limit(limit).all()
    return [
        {"id": s.id, "clock": s.clock, "size_bytes": s.size_bytes,
         "is_current": s.is_current, "created_at": str(s.created_at)}
        for s in snapshots
    ]
