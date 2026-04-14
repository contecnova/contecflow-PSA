from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.db.base import Base


class TenantPolicyPack(Base):
    __tablename__ = "tenant_policy_packs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    pack_key = Column(String(80), nullable=False, index=True)  # access_baseline | password_strict | data_retention
    pack_version = Column(String(20), nullable=False, default="1.0")
    is_enabled = Column(Boolean, nullable=False, default=True)
    config_json = Column(Text, nullable=True)  # JSON overrides
    updated_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    organization = relationship("Organization", foreign_keys=[organization_id])
    updater = relationship("User", foreign_keys=[updated_by])


class ComplianceEvidence(Base):
    __tablename__ = "compliance_evidence"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    framework = Column(String(30), nullable=False, index=True)  # SOC2 | ISO27001
    control_id = Column(String(50), nullable=False, index=True)
    evidence_type = Column(String(30), nullable=False)  # policy | screenshot | report | ticket | audit_log
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    artifact_uri = Column(String(1000), nullable=True)
    artifact_hash = Column(String(128), nullable=True)
    metadata_json = Column(Text, nullable=True)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    organization = relationship("Organization", foreign_keys=[organization_id])
    creator = relationship("User", foreign_keys=[created_by])
