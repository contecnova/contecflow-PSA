"""
Document Collaboration Endpoints — CRDT snapshot save/load/history for collaborative editing.
"""
from fastapi import APIRouter, Depends, HTTPException, Request

from sqlalchemy.orm import Session
from app.core.deps import get_db, get_current_user
from app.models.user import User
from app.models.document_collab import DocumentCollabSnapshot
from app.models.documents import Document
from sqlalchemy import desc
import base64

router = APIRouter(prefix="/documents", tags=["documents"])


# Save a new CRDT snapshot for a document (raw bytes, Content-Type: application/octet-stream)
@router.post("/{doc_id}/collab/snapshot", summary="Save collaborative doc snapshot")
async def save_collab_snapshot(
    doc_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")
    # Read raw body as bytes
    snapshot = await request.body()
    if not snapshot:
        raise HTTPException(400, "Missing snapshot body")
    # Lamport clock: auto-increment
    prev = db.query(DocumentCollabSnapshot).filter_by(document_id=doc_id, is_current=True).order_by(desc(DocumentCollabSnapshot.clock)).first()
    clock = (prev.clock + 1) if prev else 1
    db.query(DocumentCollabSnapshot).filter_by(document_id=doc_id, is_current=True).update({"is_current": False})
    snap = DocumentCollabSnapshot(
        document_id=doc_id,
        state_vector=snapshot,
        clock=clock,
        size_bytes=len(snapshot),
        is_current=True,
        created_by=current_user.id,
    )
    db.add(snap)
    db.commit()
    return {"id": snap.id, "document_id": doc_id, "clock": snap.clock, "size_bytes": snap.size_bytes}


# Load the latest CRDT snapshot for a document
@router.get("/{doc_id}/collab/snapshot", summary="Load latest collaborative doc snapshot")
def load_collab_snapshot(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")
    snap = db.query(DocumentCollabSnapshot).filter_by(document_id=doc_id, is_current=True).order_by(desc(DocumentCollabSnapshot.clock)).first()
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
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")
    snaps = db.query(DocumentCollabSnapshot).filter_by(document_id=doc_id).order_by(desc(DocumentCollabSnapshot.clock)).all()
    return [{"id": s.id, "clock": s.clock, "created_at": s.created_at, "size_bytes": s.size_bytes} for s in snaps]
