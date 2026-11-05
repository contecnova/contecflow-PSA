"""
Document Collaboration Endpoints — CRDT snapshot save/load/history for collaborative editing.
"""
import base64

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db, require_internal_user
from app.core.responses import APIListResponse
from app.models.user import User
from app.services.documents_collab_service import (
    save_collab_snapshot as svc_save_snapshot,
    load_collab_snapshot as svc_load_snapshot,
    get_collab_history as svc_get_history,
)

router = APIRouter(prefix="/documents", tags=["documents"])


def _puede_leer(db, doc_id, usuario) -> None:
    from app.services.documents_service import check_document_access, get_document_or_404 as _doc
    check_document_access(_doc(db, doc_id, usuario), usuario)


def _puede_escribir(db, doc_id, usuario) -> None:
    from app.models.documents import DocumentAccessLevel
    from app.services import reserva_de_documentos
    from app.services.documents_service import check_document_access, get_document_or_404 as _doc
    doc = _doc(db, doc_id, usuario)
    check_document_access(doc, usuario, DocumentAccessLevel.editor)
    reserva_de_documentos.exigir_libre(doc, usuario)


# Save a new CRDT snapshot for a document (raw bytes, Content-Type: application/octet-stream)
@router.post("/{doc_id}/collab/snapshot", summary="Save collaborative doc snapshot")
async def save_collab_snapshot(
    doc_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: dominio: los documentos ya tienen permisos por documento; el rol solo excluye al externo
):
    # Audit #C7: async is required to read the raw body without blocking; DB
    # work is delegated to the threadpool via `run_db`.
    from app.core.async_db import run_db
    # Revisión 2026-11: antes no se miraba el permiso del documento (cualquier
    # interno de la empresa podía escribir en cualquiera) ni la reserva.
    await run_db(_puede_escribir, db, doc_id, current_user)
    snapshot = await request.body()
    if not snapshot:
        raise HTTPException(400, "Missing snapshot body")
    snap = await run_db(svc_save_snapshot, db, doc_id, snapshot, current_user.id)
    return {"id": snap.id, "document_id": doc_id, "clock": snap.clock, "size_bytes": snap.size_bytes}


# Load the latest CRDT snapshot for a document
@router.get("/{doc_id}/collab/snapshot", summary="Load latest collaborative doc snapshot")
def load_collab_snapshot(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _puede_leer(db, doc_id, current_user)   # revisión 2026-11: antes sin permiso del documento
    snap = svc_load_snapshot(db, doc_id)
    if not snap:
        return {"snapshot": None, "clock": 0}
    return {
        "state_vector_b64": base64.b64encode(snap.state_vector).decode("ascii"),
        "clock": snap.clock,
        "size_bytes": snap.size_bytes,
        "id": snap.id,
    }


# List all snapshots (history) for a document
@router.get("/{doc_id}/collab/history", summary="Get snapshot history")
def collab_snapshot_history(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _puede_leer(db, doc_id, current_user)   # revisión 2026-11: antes sin permiso del documento
    snaps = svc_get_history(db, doc_id)
    items = [{"id": s.id, "clock": s.clock, "created_at": s.created_at, "size_bytes": s.size_bytes} for s in snaps]
    return APIListResponse.ok(items=items, total=len(items))
