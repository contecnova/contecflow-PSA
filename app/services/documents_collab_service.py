"""
documents_collab_service.py — Business logic for CRDT collaborative document snapshots.

Exported functions:
  save_collab_snapshot(db, doc_id, snapshot_bytes, user_id) -> DocumentCollabSnapshot
  load_collab_snapshot(db, doc_id) -> DocumentCollabSnapshot | None
  get_collab_history(db, doc_id) -> list[DocumentCollabSnapshot]
  get_document_or_404(db, doc_id) -> Document
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.document_collab import DocumentCollabSnapshot
from app.models.documents import Document


def get_document_or_404(db: Session, doc_id: str) -> Document:
    """Fetch a Document by id, raising 404 if not found."""
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")
    return doc


def save_collab_snapshot(
    db: Session,
    doc_id: str,
    snapshot_bytes: bytes,
    user_id: str,
) -> DocumentCollabSnapshot:
    """
    Persist a new CRDT snapshot for a document.

    - Auto-increments the Lamport clock relative to the current snapshot.
    - Marks all previous snapshots as not-current.
    - Returns the newly created snapshot (already committed).
    """
    prev = (
        db.query(DocumentCollabSnapshot)
        .filter_by(document_id=doc_id, is_current=True)
        .order_by(desc(DocumentCollabSnapshot.clock))
        .first()
    )
    clock = (prev.clock + 1) if prev else 1

    db.query(DocumentCollabSnapshot).filter_by(
        document_id=doc_id, is_current=True
    ).update({"is_current": False})

    snap = DocumentCollabSnapshot(
        document_id=doc_id,
        state_vector=snapshot_bytes,
        clock=clock,
        size_bytes=len(snapshot_bytes),
        is_current=True,
        created_by=user_id,
    )
    db.add(snap)
    db.commit()
    return snap


def load_collab_snapshot(db: Session, doc_id: str) -> Optional[DocumentCollabSnapshot]:
    """Return the current CRDT snapshot for a document, or None if none exists."""
    return (
        db.query(DocumentCollabSnapshot)
        .filter_by(document_id=doc_id, is_current=True)
        .order_by(desc(DocumentCollabSnapshot.clock))
        .first()
    )


def get_collab_history(db: Session, doc_id: str) -> List[DocumentCollabSnapshot]:
    """Return all snapshots for a document, most-recent first."""
    return (
        db.query(DocumentCollabSnapshot)
        .filter_by(document_id=doc_id)
        .order_by(desc(DocumentCollabSnapshot.clock))
        .all()
    )
