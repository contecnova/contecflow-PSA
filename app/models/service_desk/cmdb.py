"""service_desk.cmdb models — split from the former 1385-LOC god-file."""

from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Boolean, Enum, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.db.base import Base


from app.models.service_desk._enums import CIRelationType, CIStatus, CIType

class ConfigurationItem(Base):
    __tablename__ = "sd_configuration_items"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    is_active = Column(Boolean, default=True, nullable=False, server_default="1", index=True)  # audit #36 soft-delete
    code = Column(String(30), nullable=False)  # unique per-tenant (ver __table_args__)
    name = Column(String(255), nullable=False)
    ci_type = Column(Enum(CIType), nullable=False)
    status = Column(Enum(CIStatus), default=CIStatus.operational)
    description = Column(Text, nullable=True)

    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True)
    owner_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    environment = Column(String(50), nullable=True)

    version = Column(String(50), nullable=True)
    location = Column(String(255), nullable=True)
    vendor = Column(String(100), nullable=True)

    sla_policy_id = Column(String(36), ForeignKey("sd_sla_policies.id"), nullable=True)

    criticality = Column(String(20), default="medium")
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # audit #38: unique per-tenant
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_sd_ci_code_per_org"),
    )

    project = relationship("Project", foreign_keys=[project_id])
    owner = relationship("User", foreign_keys=[owner_user_id])
    sla_policy = relationship("SLAPolicy")

class CIRelation(Base):
    __tablename__ = "sd_ci_relations"

    id            = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    source_ci_id  = Column(String(36), ForeignKey("sd_configuration_items.id", ondelete="CASCADE"), nullable=False, index=True)
    target_ci_id  = Column(String(36), ForeignKey("sd_configuration_items.id", ondelete="CASCADE"), nullable=False, index=True)
    relation_type = Column(Enum(CIRelationType), nullable=False)
    notes         = Column(String(255), nullable=True)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())

    source_ci = relationship("ConfigurationItem", foreign_keys=[source_ci_id])
    target_ci = relationship("ConfigurationItem", foreign_keys=[target_ci_id])
