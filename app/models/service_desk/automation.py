"""service_desk.automation models — split from the former 1385-LOC god-file."""

import sqlalchemy as sa
from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Text, Boolean, Integer, Enum, UniqueConstraint
from sqlalchemy.orm import relationship, synonym
from sqlalchemy.sql import func
import enum
import uuid
from app.db.base import Base
from app.core.config import settings


class AutonomousPlaybook(Base):
    """Configurable resolution playbooks for the autonomous agent service."""
    __tablename__ = "sd_autonomous_playbooks"

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    name            = Column(String(255), nullable=False)
    playbook_type   = Column(String(50), nullable=False, index=True)
    description     = Column(Text, nullable=True)
    steps_json      = Column(Text, nullable=True)       # JSON list of step dicts
    conditions_json = Column(Text, nullable=True)       # JSON trigger conditions
    is_active       = Column(Boolean, default=True)
    success_count   = Column(Integer, default=0)
    failure_count   = Column(Integer, default=0)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())

class AutonomousPlaybookExecution(Base):
    """Audit log of every autonomous playbook run."""
    __tablename__ = "sd_autonomous_playbook_executions"

    id               = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    ticket_id        = Column(String(36), ForeignKey("sd_tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    playbook_type    = Column(String(50), nullable=False)
    status           = Column(String(20), default="success")   # success|failed|skipped
    confidence_score = Column(Float, nullable=True)
    resolution_note  = Column(Text, nullable=True)
    error_message    = Column(Text, nullable=True)
    executed_at      = Column(DateTime(timezone=True), server_default=func.now())
    triggered_by     = Column(String(20), default="celery")    # celery|api|manual

    ticket = relationship("Ticket", foreign_keys=[ticket_id])
