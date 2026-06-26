"""
Document Collaboration Endpoints — CRDT snapshot save/load/history for collaborative editing.
"""
import base64

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_current_user
from app.models.user import User
from app.services.documents_collab_service import (
    get_document_or_404,
    save_collab_snapshot as svc_save_snapshot,
    load_collab_snapshot as svc_load_snapshot,
    get_collab_history as svc_get_history,
)

router = APIRouter(prefix="/documents", tags=["documents"])


# Save a new CRDT snapshot for a document (raw bytes, Content-Type: application/octet-stream)
@router.post("/{doc_id}/collab/snapshot", summary="Save collaborative doc snapshot")
async def save_collab_snapshot(
    doc_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Audit #C7: async is required to read the raw body without blocking; DB
    # work is delegated to the threadpool via `run_db`.
    from app.core.async_db import run_db
    await run_db(get_document_or_404, db, doc_id)
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
    get_document_or_404(db, doc_id)
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
    get_document_or_404(db, doc_id)
    snaps = svc_get_history(db, doc_id)
    return [{"id": s.id, "clock": s.clock, "created_at": s.created_at, "size_bytes": s.size_bytes} for s in snaps]
