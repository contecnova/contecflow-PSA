"""
Document collaboration snapshots — CRDT state persistence for Contecflow.
Stores Yjs/CRDT binary state vectors so collaborative editing survives server restarts.
"""
from sqlalchemy import Column, String, DateTime, LargeBinary, Integer, Boolean, Text
from sqlalchemy.sql import func
import uuid
from app.db.base import Base


class DocumentCollabSnapshot(Base):
    """
    Persisted Yjs document state. Each row is a full binary snapshot of the CRDT state
    for a document. On server restart, the y-websocket provider loads this snapshot
    instead of starting from an empty document.
    """
    __tablename__ = "document_collab_snapshots"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id  = Column(String(36), nullable=False, index=True)
    state_vector = Column(LargeBinary, nullable=False)  # Full Yjs binary state vector
    clock        = Column(Integer, default=0)            # Lamport clock / version counter
    size_bytes   = Column(Integer, default=0)
    is_current   = Column(Boolean, default=True, index=True)
    created_by   = Column(String(36), nullable=True)    # user_id who triggered snapshot
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
    metadata_json = Column(Text, nullable=True)          # JSON: {editor, clients_count, etc.}
