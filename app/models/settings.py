from sqlalchemy import Column, String, Boolean, Text, DateTime, Integer, Date, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
import uuid
from app.db.base import Base


class AppSetting(Base):
    """Key-value settings store.

    Rows with ``organization_id=NULL`` are global/system-level defaults.
    Rows with a non-NULL ``organization_id`` are tenant-specific overrides
    (e.g. per-tenant Jira URL, M365 tenant ID).
    Queries for a tenant return *both* global and tenant-specific rows so
    callers can prefer the tenant value and fall back to the global default.
    The composite unique index on (key, organization_id) enforces uniqueness.
    """
    __tablename__ = "app_settings"
    # Flag consumed by TenantSession: include global (org_id IS NULL) rows
    # alongside tenant-specific ones instead of strict == filtering.
    _tenant_filter_include_global = True

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"),
                             nullable=True, index=True)
    key             = Column(String(100), nullable=False, index=True)
    value           = Column(Text, nullable=True)
    description     = Column(String(255), nullable=True)
    updated_at      = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("key", "organization_id", name="uq_app_settings_key_org"),
    )


class CustomProjectType(Base):
    __tablename__ = "custom_project_types"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    value = Column(String(50), unique=True, nullable=False)
    label = Column(String(100), nullable=False)
    color = Column(String(20), default="#7a8aaa")
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CustomProjectStatus(Base):
    __tablename__ = "custom_project_statuses"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    value = Column(String(50), unique=True, nullable=False)
    label = Column(String(100), nullable=False)
    color = Column(String(20), default="#7a8aaa")
    is_active = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CustomTaskStatus(Base):
    __tablename__ = "custom_task_statuses"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    value = Column(String(50), unique=True, nullable=False)
    label = Column(String(100), nullable=False)
    color = Column(String(20), default="#7a8aaa")
    is_active = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Department(Base):
    __tablename__ = "departments"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), unique=True, nullable=False)
    description = Column(String(255), nullable=True)
    manager_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Holiday(Base):
    __tablename__ = "holidays"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), nullable=False)
    date = Column(Date, nullable=False)
    type = Column(String(20), default="public")
    applies_to = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
