"""service_desk.catalog models — split from the former 1385-LOC god-file."""

from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Text, Boolean, Integer, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.db.base import Base
from app.core.config import settings


from app.models.service_desk._enums import SupportLevel, TicketPriority, TicketType

class ServiceCategory(Base):
    __tablename__ = "sd_service_categories"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    icon = Column(String(10), default="🔧")
    color = Column(String(20), default="#00d4ff")
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    services = relationship("ServiceItem", back_populates="category",
                            cascade="all, delete-orphan",
                            order_by="ServiceItem.sort_order")

class ServiceItem(Base):
    __tablename__ = "sd_service_items"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    category_id = Column(String(36), ForeignKey("sd_service_categories.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    ticket_type = Column(Enum(TicketType), default=TicketType.service_request)
    default_priority = Column(Enum(TicketPriority), default=TicketPriority.p3_medium)
    default_support_level = Column(Enum(SupportLevel), default=SupportLevel.l1)

    sla_response_hours = Column(Float, default=settings.SLA_P3_RESPONSE_HOURS)
    sla_resolution_hours = Column(Float, default=settings.SLA_P3_RESOLUTION_HOURS)

    custom_fields = Column(Text, nullable=True)

    auto_assign_group = Column(String(100), nullable=True)
    requires_approval = Column(Boolean, default=False)
    approval_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)

    is_active = Column(Boolean, default=True)
    is_visible_to_clients = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    category = relationship("ServiceCategory", back_populates="services")
    approver = relationship("User", foreign_keys=[approval_user_id])

class SLAPolicy(Base):
    __tablename__ = "sd_sla_policies"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    name = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    is_default = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)

    p1_response_hours = Column(Float, default=settings.SLA_P1_RESPONSE_HOURS)
    p1_resolution_hours = Column(Float, default=settings.SLA_P1_RESOLUTION_HOURS)
    p2_response_hours = Column(Float, default=settings.SLA_P2_RESPONSE_HOURS)
    p2_resolution_hours = Column(Float, default=settings.SLA_P2_RESOLUTION_HOURS)
    p3_response_hours = Column(Float, default=settings.SLA_P3_RESPONSE_HOURS)
    p3_resolution_hours = Column(Float, default=settings.SLA_P3_RESOLUTION_HOURS)
    p4_response_hours = Column(Float, default=settings.SLA_P4_RESPONSE_HOURS)
    p4_resolution_hours = Column(Float, default=settings.SLA_P4_RESOLUTION_HOURS)

    business_hours_only = Column(Boolean, default=True)
    business_start = Column(Integer, default=9)
    business_end = Column(Integer, default=18)
    business_days = Column(String(20), default="1,2,3,4,5")  # ISO: 1 = lunes ... 7 = domingo
    # Zona IANA de la jornada; NULL usa DEFAULT_TIMEZONE de la organización.
    timezone = Column(String(64), nullable=True)
    # Calendario de servicio (jornada, zona y festivos) que manda sobre los
    # `business_*` de arriba. NULL: se usan los de la propia política.
    calendar_id = Column(String(36), ForeignKey("sla_calendars.id", ondelete="SET NULL"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
