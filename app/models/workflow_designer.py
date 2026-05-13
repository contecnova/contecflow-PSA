"""
Visual Workflow Designer models for Service Desk declarative automation.
"""
from __future__ import annotations

import enum
import uuid

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Index, Integer, JSON, String, Text
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
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
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
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
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


# ── Runtime ──────────────────────────────────────────────────────────────────
class WorkflowRunStatus(str, enum.Enum):
    running = "running"
    waiting = "waiting"      # bloqueado por aprobación / espera temporal
    completed = "completed"
    cancelled = "cancelled"
    error = "error"


class WorkflowRun(Base):
    """Una ejecución concreta de un blueprint sobre una entidad (ticket / cambio
    / aprobación) o ad-hoc.  El motor avanza el `current_node_id` paso a paso."""
    __tablename__ = "sd_workflow_runs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)

    blueprint_id = Column(String(36), ForeignKey("sd_workflow_blueprints.id", ondelete="CASCADE"),
                          nullable=False, index=True)
    blueprint_version_id = Column(String(36), ForeignKey("sd_workflow_blueprint_versions.id", ondelete="SET NULL"),
                                  nullable=True)
    blueprint_version = Column(Integer, nullable=False)

    target_entity_type = Column(String(40), nullable=True)   # ticket | change | approval | manual
    target_entity_id = Column(String(36), nullable=True, index=True)

    status = Column(Enum(WorkflowRunStatus), nullable=False, default=WorkflowRunStatus.running, index=True)
    current_node_id = Column(String(120), nullable=True)
    wake_at = Column(DateTime(timezone=True), nullable=True, index=True)  # para wait/timer
    last_error = Column(Text, nullable=True)

    context_json = Column(JSON, nullable=False, default=dict)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    blueprint = relationship("WorkflowBlueprint")
    steps = relationship(
        "WorkflowRunStep",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="WorkflowRunStep.created_at",
    )

    __table_args__ = (
        Index("ix_sd_workflow_runs_blueprint_status", "blueprint_id", "status"),
    )


class WorkflowRunStepStatus(str, enum.Enum):
    done = "done"
    waiting = "waiting"
    error = "error"


class WorkflowRunStep(Base):
    """Trazabilidad: cada nodo visitado por el motor queda registrado con el
    branch tomado, payload y timestamps. Sirve también de cola para nodos que
    quedaron en 'waiting' (aprobaciones, etc.)."""
    __tablename__ = "sd_workflow_run_steps"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    run_id = Column(String(36), ForeignKey("sd_workflow_runs.id", ondelete="CASCADE"),
                    nullable=False, index=True)
    node_id = Column(String(120), nullable=False)
    node_type = Column(String(40), nullable=False)
    status = Column(Enum(WorkflowRunStepStatus), nullable=False, default=WorkflowRunStepStatus.done)
    branch_taken = Column(String(40), nullable=True)
    payload_json = Column(JSON, nullable=False, default=dict)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    run = relationship("WorkflowRun", back_populates="steps")
