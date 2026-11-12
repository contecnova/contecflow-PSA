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
    id: str = Field(..., description="Identificador único de la versión")
    version_num: int = Field(..., description="Número secuencial de la versión")
    file_name: str = Field(..., description="Nombre del archivo subido")
    file_size: Optional[int] = Field(default=None, description="Tamaño del archivo en bytes")
    file_mime_type: Optional[str] = Field(default=None, description="Tipo MIME del archivo")
    change_note: Optional[str] = Field(default=None, description="Nota de cambio asociada a la versión")
    uploader_id: str = Field(..., description="ID del usuario que subió la versión")
    uploader_name: str = Field(..., description="Nombre del usuario que subió la versión")
    created_at: datetime = Field(..., description="Fecha de creación de la versión")
    # download_url is the canonical field used by the frontend.
    # s3_url is kept for backward compatibility (same value).
    download_url: Optional[str] = Field(default=None, description="URL de descarga del archivo")
    s3_url: Optional[str] = Field(default=None, description="URL S3 mantenida por compatibilidad")

    class Config:
        from_attributes = True


# ── Permission Schemas ─────────────────────────────────────────────────────

class DocumentPermissionOut(BaseModel):
    id: str = Field(..., description="Identificador único del permiso")
    # One of these three identifies the subject of the grant
    user_id: Optional[str] = Field(default=None, description="ID del usuario beneficiario del permiso")
    user_name: Optional[str] = Field(default=None, description="Nombre del usuario beneficiario del permiso")
    role: Optional[str] = Field(default=None, description="Rol al que se concede el permiso")
    department: Optional[str] = Field(default=None, description="Departamento al que se concede el permiso")
    access_level: DocumentAccessLevel = Field(..., description="Nivel de acceso concedido")
    granted_by_name: Optional[str] = Field(default=None, description="Nombre de quien concedió el permiso")
    granted_at: datetime = Field(..., description="Fecha en que se concedió el permiso")
    expires_at: Optional[datetime] = Field(default=None, description="Fecha de expiración del permiso")

    class Config:
        from_attributes = True


class DocumentPermissionCreate(BaseModel):
    """Grant access to a document. Provide exactly ONE of user_id / role / department."""
    user_id: Optional[str] = Field(default=None, description="ID del usuario al que se concede acceso")
    role: Optional[str] = Field(default=None, description="Rol al que se concede acceso (p. ej. pm, team_lead)")
    department: Optional[str] = Field(default=None, description="Departamento al que se concede acceso")
    access_level: DocumentAccessLevel = Field(..., description="Nivel de acceso a otorgar")
    expires_at: Optional[datetime] = Field(default=None, description="Fecha de expiración del permiso")


# ── Main Document Schemas ──────────────────────────────────────────────────

class DocumentBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255, description="Título del documento")
    description: Optional[str] = Field(default=None, description="Descripción del documento")
    category: DocumentCategory = Field(default=DocumentCategory.other, description="Categoría del documento")
    requires_approval: bool = Field(default=False, description="Indica si el documento requiere aprobación")


class DocumentCreate(DocumentBase):
    project_id: Optional[str] = Field(default=None, description="ID del proyecto asociado al documento")
    client_id: Optional[str] = Field(default=None, description="ID del cliente asociado al documento")
    milestone_id: Optional[str] = Field(default=None, description="ID del milestone asociado al documento")


class DocumentUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255, description="Título del documento")
    description: Optional[str] = Field(default=None, description="Descripción del documento")
    category: Optional[DocumentCategory] = Field(default=None, description="Categoría del documento")
    requires_approval: Optional[bool] = Field(default=None, description="Indica si requiere aprobación")
    is_archived: Optional[bool] = Field(default=None, description="Indica si el documento está archivado")


class DocumentOut(DocumentBase):
    id: str = Field(..., description="Identificador único del documento")
    project_id: Optional[str] = Field(default=None, description="ID del proyecto asociado")
    client_id: Optional[str] = Field(default=None, description="ID del cliente asociado")
    milestone_id: Optional[str] = Field(default=None, description="ID del milestone asociado")
    approval_status: ApprovalStatus = Field(..., description="Estado de aprobación del documento")
    requires_approval: bool = Field(..., description="Indica si el documento requiere aprobación")
    is_archived: bool = Field(..., description="Indica si el documento está archivado")
    created_by: str = Field(..., description="ID del usuario que creó el documento")
    created_by_name: str = Field(..., description="Nombre del usuario que creó el documento")
    updated_by: Optional[str] = Field(default=None, description="ID del último usuario que actualizó el documento")
    updated_by_name: Optional[str] = Field(default=None, description="Nombre del último usuario que actualizó el documento")
    approved_by: Optional[str] = Field(default=None, description="ID del usuario que aprobó el documento")
    approved_by_name: Optional[str] = Field(default=None, description="Nombre del usuario que aprobó el documento")
    approved_at: Optional[datetime] = Field(default=None, description="Fecha de aprobación del documento")
    created_at: datetime = Field(..., description="Fecha de creación del documento")
    updated_at: Optional[datetime] = Field(default=None, description="Fecha de la última actualización")
    ai_summary: Optional[str] = Field(default=None, description="Resumen generado por IA del documento")
    versions: List[DocumentVersionOut] = Field(default=[], description="Lista de versiones del documento")
    permissions: List[DocumentPermissionOut] = Field(default=[], description="Lista de permisos sobre el documento")
    tags: List[str] = Field(default=[], description="Etiquetas asociadas al documento")
    approval_request: Optional[dict] = Field(default=None, description="Datos de la solicitud de aprobación si existe")
    checkout: Optional[dict] = Field(default=None, description="Reserva para editar vigente: quién, desde y hasta cuándo, y si es tuya")

    class Config:
        from_attributes = True


class DocumentListOut(BaseModel):
    id: str = Field(..., description="Identificador único del documento")
    title: str = Field(..., description="Título del documento")
    category: DocumentCategory = Field(..., description="Categoría del documento")
    is_archived: bool = Field(..., description="Indica si el documento está archivado")
    requires_approval: bool = Field(default=False, description="Indica si el documento requiere aprobación")
    approval_status: ApprovalStatus = Field(..., description="Estado de aprobación del documento")
    created_by_name: str = Field(..., description="Nombre del usuario que creó el documento")
    created_at: datetime = Field(..., description="Fecha de creación del documento")
    updated_at: Optional[datetime] = Field(default=None, description="Fecha de la última actualización")
    latest_version: Optional[DocumentVersionOut] = Field(default=None, description="Última versión disponible del documento")
    checkout: Optional[dict] = Field(default=None, description="Reserva para editar vigente (quién y hasta cuándo)")
    # Auditoria 2026-11: los serializadores del listado los calculaban y el esquema los
    # descartaba, asi que las etiquetas, el filtro por etiqueta y la insignia «vN» no salian.
    tags: List[str] = Field(default=[], description="Etiquetas asociadas al documento")
    version_count: int = Field(default=0, description="Número de versiones del documento")

    class Config:
        from_attributes = True


# ── File Upload Schemas ────────────────────────────────────────────────────

class DocumentVersionCreate(BaseModel):
    change_note: Optional[str] = Field(None, max_length=500, description="Nota de cambio asociada a la nueva versión")


class DocumentApprovalPayload(BaseModel):
    status: ApprovalStatus = Field(default=ApprovalStatus.approved, description="Estado final de la aprobación")
    note: Optional[str] = Field(default=None, description="Nota o comentario de la decisión de aprobación")
    notes: Optional[str] = Field(default=None, description="Notas adicionales sobre la aprobación")


# ── Search/Filter Schemas ──────────────────────────────────────────────────

class DocumentFilterParams(BaseModel):
    category: Optional[DocumentCategory] = Field(default=None, description="Filtrar por categoría de documento")
    tags: Optional[List[str]] = Field(default=None, description="Filtrar por etiquetas")
    created_by_id: Optional[str] = Field(default=None, description="Filtrar por ID del creador")
    project_id: Optional[str] = Field(default=None, description="Filtrar por proyecto asociado")
    client_id: Optional[str] = Field(default=None, description="Filtrar por cliente asociado")
    is_archived: Optional[bool] = Field(default=False, description="Filtrar por estado de archivado")
    search: Optional[str] = Field(default=None, description="Texto de búsqueda libre")
    approval_status: Optional[ApprovalStatus] = Field(default=None, description="Filtrar por estado de aprobación")
