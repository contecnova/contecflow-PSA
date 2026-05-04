"""
Document Management models – central document repository with versioning and access control.
"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Boolean, Integer, Enum, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
import uuid
from app.db.base import Base


# ── Enums ──────────────────────────────────────────────────────────────────

class DocumentCategory(str, enum.Enum):
    contract = "contract"
    deliverable = "deliverable"
    proposal = "proposal"
    sop = "sop"
    requirements = "requirements"
    meeting_notes = "meeting_notes"
    legal = "legal"
    other = "other"


class DocumentAccessLevel(str, enum.Enum):
    viewer = "viewer"      # Read-only
    editor = "editor"      # Can edit metadata and upload versions
    admin = "admin"        # Full control including permissions


class ApprovalStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


# ── Main Document ─────────────────────────────────────────────────────────

class Document(Base):
    """
    Central document entity. Can be linked to projects, clients, milestones.
    Supports versioning and granular access control.
    """
    __tablename__ = "documents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Metadata
    title = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    category = Column(Enum(DocumentCategory), default=DocumentCategory.other, index=True)

    # Relationships (optional - document can exist independently)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    client_id = Column(String(36), ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True)
    milestone_id = Column(String(36), ForeignKey("project_milestones.id", ondelete="SET NULL"), nullable=True, index=True)
    task_id = Column(String(36), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    ticket_id = Column(String(36), ForeignKey("sd_tickets.id", ondelete="SET NULL"), nullable=True, index=True)

    # Approval workflow (optional per document)
    requires_approval = Column(Boolean, default=False)
    approval_status = Column(Enum(ApprovalStatus), default=ApprovalStatus.pending)
    approved_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    # Link to the active ApprovalRequest in the multi-level approval engine
    approval_request_id = Column(String(36), ForeignKey("approval_requests.id", ondelete="SET NULL"), nullable=True, index=True)

    # Metadata
    is_archived = Column(Boolean, default=False, index=True)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=False, index=True)
    updated_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    project = relationship("Project", foreign_keys=[project_id])
    client = relationship("Client", foreign_keys=[client_id])
    milestone = relationship("ProjectMilestone", foreign_keys=[milestone_id])
    task = relationship("Task", foreign_keys=[task_id])
    ticket = relationship("Ticket", foreign_keys=[ticket_id])
    creator = relationship("User", foreign_keys=[created_by], primaryjoin="Document.created_by == User.id")
    updater = relationship("User", foreign_keys=[updated_by], primaryjoin="Document.updated_by == User.id")
    approver = relationship("User", foreign_keys=[approved_by], primaryjoin="Document.approved_by == User.id")
    versions = relationship("DocumentVersion", back_populates="document", cascade="all, delete-orphan", order_by="DocumentVersion.version_num.desc()")
    permissions = relationship("DocumentPermission", back_populates="document", cascade="all, delete-orphan")
    tags = relationship("DocumentTag", back_populates="document", cascade="all, delete-orphan")

    __table_args__ = (
        Index('ix_documents_project_created', 'project_id', 'created_at'),
        Index('ix_documents_client_created', 'client_id', 'created_at'),
    )


# ── Document Version ───────────────────────────────────────────────────────

class DocumentVersion(Base):
    """
    Immutable version history. Each upload creates a new version.
    Stores S3 file key for retrieval.
    """
    __tablename__ = "document_versions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)

    # Version number (1, 2, 3, ...)
    version_num = Column(Integer, nullable=False)

    # File metadata
    file_key = Column(String(500), nullable=False)  # S3 object key (not full URL)
    file_name = Column(String(255), nullable=False)
    file_size = Column(Integer, nullable=True)  # bytes
    file_mime_type = Column(String(100), nullable=True)  # e.g., application/pdf

    # Pre-signed URL (generated on-demand, expires in 24 hours)
    s3_url = Column(String(1000), nullable=True)
    s3_url_expires_at = Column(DateTime(timezone=True), nullable=True)

    # Change tracking
    change_note = Column(String(500), nullable=True)  # Why this version was uploaded
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    # Relationships
    document = relationship("Document", back_populates="versions")
    uploader = relationship("User", foreign_keys=[created_by])


# ── Document Permission ────────────────────────────────────────────────────

class DocumentPermission(Base):
    """
    Granular access control per user. Three-level: viewer, editor, admin.
    """
    __tablename__ = "document_permissions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Access level
    access_level = Column(Enum(DocumentAccessLevel), nullable=False)

    # Audit
    granted_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    granted_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)  # Temporary access

    # Relationships
    document = relationship("Document", back_populates="permissions", foreign_keys=[document_id])
    user = relationship("User", foreign_keys=[user_id])
    grantor = relationship("User", foreign_keys=[granted_by])

    __table_args__ = (
        Index('ix_doc_perm_document_user', 'document_id', 'user_id'),
    )


# ── Document Tag ───────────────────────────────────────────────────────────

class DocumentTag(Base):
    """
    Lightweight tagging for document organization and search.
    """
    __tablename__ = "document_tags"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    tag_name = Column(String(100), nullable=False, index=True)

    # Relationships
    document = relationship("Document", back_populates="tags")


# ── Document Access Log ───────────────────────────────────────────────────

class DocumentAccessLog(Base):
    """
    Immutable audit trail of every document view and download action.
    """
    __tablename__ = "document_access_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    action = Column(String(20), nullable=False)  # "view" | "download"
    accessed_at = Column(DateTime(timezone=True), server_default=func.now())
    ip_address = Column(String(64), nullable=True)

    document = relationship("Document")
    user = relationship("User")
