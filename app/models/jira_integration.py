"""
Jira SM Integration — models for bidirectional sync with Jira Service Management.

Tables:
  sd_jira_configs        — Per-tenant Jira connection configuration
  sd_jira_sync_map       — Ticket ↔ Jira Issue ID mapping with sync state
  sd_jira_sync_log       — Audit log of every sync event
  sd_jira_field_map      — Custom field mapping between Contecflow and Jira
"""
from __future__ import annotations

import enum
import uuid

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, ForeignKey, Integer, String, Text, false
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class JiraSyncDirection(str, enum.Enum):
    contecflow_to_jira = "contecflow_to_jira"
    jira_to_contecflow = "jira_to_contecflow"
    bidirectional = "bidirectional"


class JiraSyncStatus(str, enum.Enum):
    pending = "pending"
    synced = "synced"
    conflict = "conflict"
    error = "error"
    skipped = "skipped"


class JiraSyncEventType(str, enum.Enum):
    created = "created"
    updated = "updated"
    status_changed = "status_changed"
    comment_synced = "comment_synced"
    attachment_synced = "attachment_synced"
    error = "error"


class JiraConfig(Base):
    """Jira connection config per organisation/tenant."""
    __tablename__ = "sd_jira_configs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    name = Column(String(100), nullable=False)

    # Connection
    jira_base_url = Column(String(500), nullable=False)   # e.g. https://myorg.atlassian.net
    jira_email = Column(String(255), nullable=False)
    # API token stored encrypted (encryption at service layer)
    jira_api_token_enc = Column(Text, nullable=False)

    # Scope
    jira_project_key = Column(String(50), nullable=False)  # e.g. SD, ITSM
    jira_issue_type_incident = Column(String(100), default="Incident")
    jira_issue_type_service_request = Column(String(100), default="Service Request")
    jira_issue_type_change = Column(String(100), default="Change")
    jira_issue_type_problem = Column(String(100), default="Problem")

    # Sync direction & filters
    sync_direction = Column(Enum(JiraSyncDirection), default=JiraSyncDirection.bidirectional)
    sync_comments = Column(Boolean, default=True)
    sync_status_changes = Column(Boolean, default=True)
    sync_priority_changes = Column(Boolean, default=True)
    sync_assignments = Column(Boolean, default=False)  # may differ per org
    sync_interval_minutes = Column(Integer, default=5)

    # Status mappings stored as JSON
    # e.g. {"new":"Open","in_progress":"In Progress","resolved":"Done"}
    status_map_json = Column(Text, nullable=True)
    priority_map_json = Column(Text, nullable=True)

    is_active = Column(Boolean, default=True)
    # Auditoria 2026-11 (#34): la conexion que usan las TAREAS de proyecto
    # (`/jira/*` y la sincronizacion periodica). Antes vivia aparte, en cuatro
    # `app_settings` (`jira_url`, `jira_email`, `jira_api_token`,
    # `jira_project_key`); la migracion 159 las trajo aqui. Una por organizacion.
    usar_para_tareas = Column(Boolean, nullable=False, default=False, server_default=false())
    last_full_sync_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)

    sync_maps = relationship("JiraSyncMap", back_populates="config",
                             cascade="all, delete-orphan")
    sync_logs = relationship("JiraSyncLog", back_populates="config",
                             cascade="all, delete-orphan")


class JiraSyncMap(Base):
    """1-to-1 mapping between a Contecflow ticket and a Jira issue."""
    __tablename__ = "sd_jira_sync_map"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    config_id = Column(String(36), ForeignKey("sd_jira_configs.id", ondelete="CASCADE"),
                       nullable=False, index=True)
    ticket_id = Column(String(36), ForeignKey("sd_tickets.id", ondelete="CASCADE"),
                       nullable=False, index=True)
    jira_issue_key = Column(String(50), nullable=False, index=True)  # e.g. SD-1234
    jira_issue_id = Column(String(50), nullable=True)

    sync_status = Column(Enum(JiraSyncStatus), default=JiraSyncStatus.pending)
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    last_jira_updated_at = Column(DateTime(timezone=True), nullable=True)
    last_ticket_updated_at = Column(DateTime(timezone=True), nullable=True)
    sync_error = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    config = relationship("JiraConfig", back_populates="sync_maps")
    ticket = relationship("Ticket", foreign_keys=[ticket_id])


class JiraSyncLog(Base):
    """Immutable audit log of every sync event."""
    __tablename__ = "sd_jira_sync_log"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    config_id = Column(String(36), ForeignKey("sd_jira_configs.id", ondelete="CASCADE"),
                       nullable=False, index=True)
    ticket_id = Column(String(36), ForeignKey("sd_tickets.id", ondelete="SET NULL"),
                       nullable=True, index=True)
    jira_issue_key = Column(String(50), nullable=True)

    event_type = Column(Enum(JiraSyncEventType), nullable=False)
    direction = Column(Enum(JiraSyncDirection), nullable=False)
    payload_json = Column(Text, nullable=True)      # diff/payload sent
    response_json = Column(Text, nullable=True)     # Jira API response
    success = Column(Boolean, nullable=False, default=True)
    error_message = Column(Text, nullable=True)

    occurred_at = Column(DateTime(timezone=True), server_default=func.now())

    config = relationship("JiraConfig", back_populates="sync_logs")
    ticket = relationship("Ticket", foreign_keys=[ticket_id])


class JiraFieldMap(Base):
    """Custom field mapping between Contecflow ticket fields and Jira custom fields."""
    __tablename__ = "sd_jira_field_map"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    config_id = Column(String(36), ForeignKey("sd_jira_configs.id", ondelete="CASCADE"),
                       nullable=False, index=True)
    contecflow_field = Column(String(100), nullable=False)   # e.g. "priority", "tags"
    jira_field_id = Column(String(100), nullable=False)      # e.g. "priority", "customfield_10020"
    transform_fn = Column(String(50), nullable=True)         # optional: "upper", "map_priority"
    is_active = Column(Boolean, default=True)

    config = relationship("JiraConfig", foreign_keys=[config_id])
