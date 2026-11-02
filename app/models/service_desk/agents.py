"""service_desk.agents models — split from the former 1385-LOC god-file."""

from sqlalchemy import Column, String, DateTime, Float, ForeignKey, Boolean, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.db.base import Base


from app.models.service_desk._enums import SupportLevel

class AgentGroup(Base):
    __tablename__ = "sd_agent_groups"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    name = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    support_level = Column(Enum(SupportLevel), nullable=False)
    # OLA: horas de calendario que tiene la cola para resolver o pasar el
    # ticket desde que le llega. Vacio: la cola no tiene OLA.
    ola_hours = Column(Float, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    members = relationship("AgentGroupMember", back_populates="group", cascade="all, delete-orphan")

class AgentGroupMember(Base):
    __tablename__ = "sd_agent_group_members"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    group_id = Column(String(36), ForeignKey("sd_agent_groups.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    is_lead = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    group = relationship("AgentGroup", back_populates="members")
    user = relationship("User", foreign_keys=[user_id])
