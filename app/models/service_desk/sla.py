"""service_desk.sla models — split from the former 1385-LOC god-file."""

import sqlalchemy as sa
from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Text, Boolean, Integer, Enum, UniqueConstraint
from sqlalchemy.orm import relationship, synonym
from sqlalchemy.sql import func
import enum
import uuid
from app.db.base import Base
from app.core.config import settings


from app.models.service_desk._enums import EscalationAction, EscalationTrigger, OnCallRotationType, SLAEventType

class SLAEvent(Base):
    __tablename__ = "sd_sla_events"

    id         = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    ticket_id  = Column(String(36), ForeignKey("sd_tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(Enum(SLAEventType), nullable=False)
    sla_type   = Column(String(20), default="resolution")  # response | resolution
    note       = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)

class SDSLAHoliday(Base):
    """Festivos en los que el SLA no corre (por política de negocio)."""
    __tablename__ = "sd_sla_holidays"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    name        = Column(String(255), nullable=False)
    holiday_date = Column(String(10), nullable=False)   # YYYY-MM-DD
    country     = Column(String(2), nullable=True)      # ISO 3166-1 alpha-2, null = global
    sla_policy_id = Column(String(36), ForeignKey("sd_sla_policies.id", ondelete="CASCADE"), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())

    sla_policy = relationship("SLAPolicy")

class EscalationRule(Base):
    """Regla de escalada automática basada en tiempo o estado del SLA."""
    __tablename__ = "sd_escalation_rules"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    name        = Column(String(255), nullable=False)
    is_active   = Column(Boolean, default=True)
    sort_order  = Column(Integer, default=100)

    # Condiciones
    trigger         = Column(Enum(EscalationTrigger), nullable=False)
    applies_to_priority = Column(String(100), nullable=True)   # JSON list of priorities, null = all
    idle_hours_threshold = Column(Float, nullable=True)        # for idle_hours trigger
    group_id        = Column(String(36), ForeignKey("sd_agent_groups.id"), nullable=True)  # solo esta cola

    # Acción
    action          = Column(Enum(EscalationAction), nullable=False)
    target_group_id = Column(String(36), ForeignKey("sd_agent_groups.id"), nullable=True)
    notify_user_ids = Column(Text, nullable=True)              # JSON: [user_id, ...]
    target_priority = Column(String(30), nullable=True)        # for elevate_priority

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    group        = relationship("AgentGroup", foreign_keys=[group_id])
    target_group = relationship("AgentGroup", foreign_keys=[target_group_id])

class EscalationLog(Base):
    """Registro de cada vez que se activó una regla de escalada."""
    __tablename__ = "sd_escalation_logs"

    id         = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    rule_id    = Column(String(36), ForeignKey("sd_escalation_rules.id"), nullable=False, index=True)
    ticket_id  = Column(String(36), ForeignKey("sd_tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    action_taken = Column(String(255), nullable=True)
    triggered_at = Column(DateTime(timezone=True), server_default=func.now())

    rule   = relationship("EscalationRule")
    ticket = relationship("Ticket")

class OnCallSchedule(Base):
    """Guardia de soporte por grupo. Define quién responde P1/P2 fuera de horario."""
    __tablename__ = "sd_oncall_schedules"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    name        = Column(String(255), nullable=False)
    group_id    = Column(String(36), ForeignKey("sd_agent_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    rotation    = Column(Enum(OnCallRotationType), default=OnCallRotationType.weekly)
    timezone    = Column(String(50), default=settings.DEFAULT_TIMEZONE)
    is_active   = Column(Boolean, default=True)
    description = Column(String(255), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())

    group   = relationship("AgentGroup")
    entries = relationship("OnCallEntry", back_populates="schedule", cascade="all, delete-orphan",
                           order_by="OnCallEntry.start_dt")

class OnCallEntry(Base):
    """Turno individual dentro de un Schedule de guardia."""
    __tablename__ = "sd_oncall_entries"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    schedule_id = Column(String(36), ForeignKey("sd_oncall_schedules.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id     = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    start_dt    = Column(DateTime(timezone=True), nullable=False)
    end_dt      = Column(DateTime(timezone=True), nullable=False)
    notes       = Column(String(255), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())

    schedule = relationship("OnCallSchedule", back_populates="entries")
    user     = relationship("User", foreign_keys=[user_id])
