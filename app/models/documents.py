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
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7

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
    approved_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    # Link to the active ApprovalRequest in the multi-level approval engine
    approval_request_id = Column(String(36), ForeignKey("approval_requests.id", ondelete="SET NULL"), nullable=True, index=True)

    # Metadata
    is_archived = Column(Boolean, default=False, index=True)
    ai_summary = Column(Text, nullable=True)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=False, index=True)
    updated_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    project = relationship("Project", foreign_keys=[project_id])  # TODO #56: inverse en Project (project.py)
    client = relationship("Client", foreign_keys=[client_id])  # TODO #56: inverse en Client (clients.py)
    milestone = relationship("ProjectMilestone", foreign_keys=[milestone_id])  # TODO #56: inverse en ProjectMilestone (otro agente)
    task = relationship("Task", foreign_keys=[task_id])  # TODO #56: inverse en Task (task.py)
    ticket = relationship("Ticket", foreign_keys=[ticket_id])  # TODO #56: inverse en Ticket (service_desk)
    creator = relationship("User", foreign_keys=[created_by], primaryjoin="Document.created_by == User.id")  # TODO #56
    updater = relationship("User", foreign_keys=[updated_by], primaryjoin="Document.updated_by == User.id")  # TODO #56
    approver = relationship("User", foreign_keys=[approved_by], primaryjoin="Document.approved_by == User.id")  # TODO #56
    # audit #56-57: versions/permissions/tags iterados SIEMPRE en _serialize_doc (documents_service.py)
    # → selectin colapsa N×3 queries en 3 IN-loads al listar documentos.
    versions = relationship("DocumentVersion", back_populates="document", cascade="all, delete-orphan", order_by="DocumentVersion.version_num.desc()", lazy="selectin")
    permissions = relationship("DocumentPermission", back_populates="document", cascade="all, delete-orphan", lazy="selectin")
    tags = relationship("DocumentTag", back_populates="document", cascade="all, delete-orphan", lazy="selectin")

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
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
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
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    # Relationships
    document = relationship("Document", back_populates="versions")
    uploader = relationship("User", foreign_keys=[created_by])  # TODO #56: inverse en User


# ── Document Permission ────────────────────────────────────────────────────

class DocumentPermission(Base):
    """
    Granular access control. Three subject types (exactly one is set per row):
      - user_id: a single user
      - role: a UserRole (e.g. "pm" → all PMs)
      - department: a free-text department name (matches User.department)
    Three access levels: viewer, editor, admin.
    """
    __tablename__ = "document_permissions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)

    # Subject — exactly one of these three is populated.
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    role = Column(String(40), nullable=True, index=True)
    department = Column(String(100), nullable=True, index=True)

    # Access level
    access_level = Column(Enum(DocumentAccessLevel), nullable=False)

    # Audit
    granted_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    granted_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)  # Temporary access

    # Relationships
    document = relationship("Document", back_populates="permissions", foreign_keys=[document_id])
    user = relationship("User", foreign_keys=[user_id])  # TODO #56: inverse en User
    grantor = relationship("User", foreign_keys=[granted_by])  # TODO #56: inverse en User

    __table_args__ = (
        Index('ix_doc_perm_document_user', 'document_id', 'user_id'),
        Index('ix_doc_perm_document_role', 'document_id', 'role'),
        Index('ix_doc_perm_document_department', 'document_id', 'department'),
    )


# ── Document Tag ───────────────────────────────────────────────────────────

class DocumentTag(Base):
    """
    Lightweight tagging for document organization and search.
    """
    __tablename__ = "document_tags"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
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
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    action = Column(String(20), nullable=False)  # "view" | "download"
    accessed_at = Column(DateTime(timezone=True), server_default=func.now())
    ip_address = Column(String(64), nullable=True)

    document = relationship("Document")  # TODO #56: inverse opcional (audit log)
    user = relationship("User")  # TODO #56: inverse en User
