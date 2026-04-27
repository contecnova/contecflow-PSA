"""
Visual Workflow Designer models for Service Desk declarative automation.
"""
from __future__ import annotations

import enum
import uuid

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class WorkflowBlueprintStatus(str, enum.Enum):
    draft = "draft"
    published = "published"
    archived = "archived"


class WorkflowBlueprint(Base):
    __tablename__ = "sd_workflow_blueprints"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    description = Column(String(500), nullable=True)
    process_type = Column(String(50), nullable=False, index=True)  # ticket|change|approval
    scope = Column(String(30), default="global")                  # global|project|client

    latest_version = Column(Integer, default=1)
    status = Column(Enum(WorkflowBlueprintStatus), default=WorkflowBlueprintStatus.draft)
    is_active = Column(Boolean, default=True)

    created_by_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    versions = relationship(
        "WorkflowBlueprintVersion",
        back_populates="blueprint",
        cascade="all, delete-orphan",
        order_by="WorkflowBlueprintVersion.version.desc()",
    )


class WorkflowBlueprintVersion(Base):
    __tablename__ = "sd_workflow_blueprint_versions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    blueprint_id = Column(String(36), ForeignKey("sd_workflow_blueprints.id", ondelete="CASCADE"),
                          nullable=False, index=True)
    version = Column(Integer, nullable=False)
    graph_json = Column(Text, nullable=False)   # {nodes:[], edges:[]}
    rules_json = Column(Text, nullable=True)    # declarative rule set compiled from graph
    is_published = Column(Boolean, default=False)
    published_at = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    blueprint = relationship("WorkflowBlueprint", back_populates="versions")
