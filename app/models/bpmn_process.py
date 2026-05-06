"""
BPMN Process Registry — central store for all business processes of the tool,
modelled in BPMN 2.0 XML and editable through the in-app BPMN editor.

Two tables:
  bpmn_processes          — one row per process (name, category, source key, latest_version)
  bpmn_process_versions   — every save creates a new version with the BPMN XML payload
"""
from __future__ import annotations

import enum
import uuid

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class BPMNProcessStatus(str, enum.Enum):
    draft = "draft"
    published = "published"
    archived = "archived"


class BPMNProcess(Base):
    __tablename__ = "bpmn_processes"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"),
                             nullable=True, index=True)

    # Identity
    key = Column(String(120), nullable=False, index=True)        # stable slug, e.g. "incident_management"
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(80), nullable=False, index=True)    # incident, change, project, finance, ai-ml…
    icon = Column(String(40), nullable=True)                     # optional emoji/icon hint

    # Source linkage — when the process is derived from an existing module
    source_kind = Column(String(40), nullable=True)              # "seeded" | "custom"
    source_ref = Column(String(255), nullable=True)              # file path or model class

    # Versioning
    latest_version = Column(Integer, default=1, nullable=False)
    status = Column(Enum(BPMNProcessStatus), default=BPMNProcessStatus.draft, nullable=False)
    is_seeded = Column(Boolean, default=False, nullable=False)   # came from initial inventory
    is_active = Column(Boolean, default=True, nullable=False)

    created_by_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    versions = relationship(
        "BPMNProcessVersion",
        back_populates="process",
        cascade="all, delete-orphan",
        order_by="BPMNProcessVersion.version.desc()",
    )


class BPMNProcessVersion(Base):
    __tablename__ = "bpmn_process_versions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    process_id = Column(String(36), ForeignKey("bpmn_processes.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    version = Column(Integer, nullable=False)

    bpmn_xml = Column(Text, nullable=False)        # BPMN 2.0 XML
    notes = Column(String(500), nullable=True)     # change description
    is_published = Column(Boolean, default=False, nullable=False)
    published_at = Column(DateTime(timezone=True), nullable=True)

    created_by_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    process = relationship("BPMNProcess", back_populates="versions")
