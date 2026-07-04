"""service_desk.changes models — split from the former 1385-LOC god-file."""

from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Text, Boolean, Integer, Enum
from sqlalchemy.orm import relationship, synonym
from sqlalchemy.sql import func
import uuid
from app.db.base import Base


from app.models.service_desk._enums import ChangeRisk, ChangeStatus, ChangeType, TicketPriority

class ITSMChangeRequest(Base):
    """Change Management ITIL completo — separado del ChangeRequest de proyectos."""
    __tablename__ = "sd_change_requests"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    number      = Column(String(20), unique=True, nullable=False, index=True, default=lambda: f"CHG-{uuid.uuid4().hex[:8].upper()}")
    title       = Column(String(500), nullable=False)
    description = Column(Text, nullable=False)

    change_type  = Column(Enum(ChangeType), nullable=False, default=ChangeType.normal)
    status       = Column(Enum(ChangeStatus), nullable=False, default=ChangeStatus.draft, index=True)
    risk         = Column(Enum(ChangeRisk), default=ChangeRisk.medium)
    priority     = Column(Enum(TicketPriority), default=TicketPriority.p3_medium)

    # Planificación
    planned_start    = Column(DateTime(timezone=True), nullable=True)
    planned_end      = Column(DateTime(timezone=True), nullable=True)
    actual_start     = Column(DateTime(timezone=True), nullable=True)
    actual_end       = Column(DateTime(timezone=True), nullable=True)

    # Plan
    implementation_plan = Column(Text, nullable=True)
    rollback_plan       = Column(Text, nullable=True)
    test_plan           = Column(Text, nullable=True)
    business_justification = Column(Text, nullable=True)

    # Impacto
    impact_description = Column(Text, nullable=True)
    affected_cis       = Column(Text, nullable=True)  # JSON: lista de CI IDs
    downtime_minutes   = Column(Integer, default=0)

    # Post-Implementation Review
    pir_notes    = Column(Text, nullable=True)
    pir_success  = Column(Boolean, nullable=True)
    pir_date     = Column(DateTime(timezone=True), nullable=True)

    # Relaciones
    requester_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    owner_id     = Column(String(36), ForeignKey("users.id"), nullable=True)
    approver_id  = Column(String(36), ForeignKey("users.id"), nullable=True)
    approved_at  = Column(DateTime(timezone=True), nullable=True)
    approved_by  = Column(String(36), ForeignKey("users.id"), nullable=True)
    rejected_reason = Column(Text, nullable=True)

    # Phase 2 — Change Impact Analysis
    auto_risk_score = Column(Float, nullable=True)
    impact_analysis_json = Column(Text, nullable=True)
    suggested_window_json = Column(Text, nullable=True)

    related_ticket_id  = Column(String(36), ForeignKey("sd_tickets.id"), nullable=True)
    related_problem_id = Column(String(36), ForeignKey("sd_problems.id"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    requester = relationship("User", foreign_keys=[requester_id])
    owner     = relationship("User", foreign_keys=[owner_id])
    approver  = relationship("User", foreign_keys=[approver_id])
    approver_user = relationship("User", foreign_keys=[approved_by])

    requester_user_id = synonym("requester_id")

    def __init__(self, **kwargs):
        legacy_priority = kwargs.get("priority")
        if isinstance(legacy_priority, str):
            priority_map = {
                "critical": TicketPriority.p1_critical,
                "high": TicketPriority.p2_high,
                "medium": TicketPriority.p3_medium,
                "low": TicketPriority.p4_low,
            }
            kwargs["priority"] = priority_map.get(legacy_priority, legacy_priority)
        super().__init__(**kwargs)

ChangeRequest = ITSMChangeRequest
