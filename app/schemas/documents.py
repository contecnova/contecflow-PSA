"""
Document schemas for request/response validation.
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class DocumentCategory(str, Enum):
    contract = "contract"
    deliverable = "deliverable"
    proposal = "proposal"
    sop = "sop"
    requirements = "requirements"
    meeting_notes = "meeting_notes"
    legal = "legal"
    other = "other"


class DocumentAccessLevel(str, Enum):
    viewer = "viewer"
    editor = "editor"
    admin = "admin"


class ApprovalStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


# ── Version Schemas ───────────────────────────────────────────────────────

class DocumentVersionOut(BaseModel):
    id: str
    version_num: int
    file_name: str
    file_size: Optional[int] = None
    file_mime_type: Optional[str] = None
    change_note: Optional[str] = None
    uploader_id: str
    uploader_name: str
    created_at: datetime
    # download_url is the canonical field used by the frontend.
    # s3_url is kept for backward compatibility (same value).
    download_url: Optional[str] = None
    s3_url: Optional[str] = None

    class Config:
        from_attributes = True


# ── Permission Schemas ─────────────────────────────────────────────────────

class DocumentPermissionOut(BaseModel):
    id: str
    user_id: str
    user_name: str
    access_level: DocumentAccessLevel
    granted_by_name: Optional[str] = None
    granted_at: datetime
    expires_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DocumentPermissionCreate(BaseModel):
    user_id: str
    access_level: DocumentAccessLevel
    expires_at: Optional[datetime] = None


# ── Main Document Schemas ──────────────────────────────────────────────────

class DocumentBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    category: DocumentCategory = DocumentCategory.other
    requires_approval: bool = False


class DocumentCreate(DocumentBase):
    project_id: Optional[str] = None
    client_id: Optional[str] = None
    milestone_id: Optional[str] = None


class DocumentUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    category: Optional[DocumentCategory] = None
    requires_approval: Optional[bool] = None
    is_archived: Optional[bool] = None


class DocumentOut(DocumentBase):
    id: str
    project_id: Optional[str] = None
    client_id: Optional[str] = None
    milestone_id: Optional[str] = None
    approval_status: ApprovalStatus
    requires_approval: bool
    is_archived: bool
    created_by: str
    created_by_name: str
    updated_by: Optional[str] = None
    updated_by_name: Optional[str] = None
    approved_by: Optional[str] = None
    approved_by_name: Optional[str] = None
    approved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    versions: List[DocumentVersionOut] = []
    permissions: List[DocumentPermissionOut] = []
    tags: List[str] = []
    approval_request: Optional[dict] = None

    class Config:
        from_attributes = True


class DocumentListOut(BaseModel):
    id: str
    title: str
    category: DocumentCategory
    is_archived: bool
    approval_status: ApprovalStatus
    created_by_name: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    latest_version: Optional[DocumentVersionOut] = None

    class Config:
        from_attributes = True


# ── File Upload Schemas ────────────────────────────────────────────────────

class DocumentVersionCreate(BaseModel):
    change_note: Optional[str] = Field(None, max_length=500)


class DocumentApprovalPayload(BaseModel):
    status: ApprovalStatus = ApprovalStatus.approved
    note: Optional[str] = None
    notes: Optional[str] = None


# ── Search/Filter Schemas ──────────────────────────────────────────────────

class DocumentFilterParams(BaseModel):
    category: Optional[DocumentCategory] = None
    tags: Optional[List[str]] = None
    created_by_id: Optional[str] = None
    project_id: Optional[str] = None
    client_id: Optional[str] = None
    is_archived: Optional[bool] = False
    search: Optional[str] = None
    approval_status: Optional[ApprovalStatus] = None
