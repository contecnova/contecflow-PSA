"""NPS (Net Promoter Score) + Client Health models."""

import enum
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.db.base import Base


class NPSCategory(str, enum.Enum):
    promoter  = "promoter"   # 9-10
    passive   = "passive"    # 7-8
    detractor = "detractor"  # 0-6


class ClientNPS(Base):
    """Respuesta NPS recogida de un cliente con su categoría (promotor/pasivo/detractor)."""
    __tablename__ = "client_nps"

    id         = Column(Integer, primary_key=True, index=True)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    client_id  = Column(String(36), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    score      = Column(Integer,  nullable=False)           # 0-10
    category   = Column(Enum(NPSCategory), nullable=False)
    comment    = Column(Text, nullable=True)
    respondent = Column(String(200), nullable=True)         # name of the person who replied
    source     = Column(String(50),  default="manual")      # manual | email | portal
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, index=True)

    client = relationship("Client", backref="nps_responses")

    def __repr__(self) -> str:
        return f"<ClientNPS id={self.id!r} score={self.score!r}>"


class ClientHealthSnapshot(Base):
    """Periodic health score snapshot (0-100) computed from multiple signals."""

    __tablename__ = "client_health_snapshots"

    id               = Column(Integer, primary_key=True, index=True)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    client_id        = Column(String(36), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    health_score     = Column(Float, nullable=False)       # 0-100
    # Component scores (all 0-100, nullable = not computed)
    nps_component    = Column(Float, nullable=True)
    delivery_component = Column(Float, nullable=True)      # on-time deliverables ratio
    budget_component   = Column(Float, nullable=True)      # budget under-spend ratio
    activity_component = Column(Float, nullable=True)      # recent tickets / interactions
    note             = Column(Text, nullable=True)
    snapshot_at      = Column(DateTime(timezone=True), default=datetime.utcnow, index=True)

    client = relationship("Client", backref="health_snapshots")

    def __repr__(self) -> str:
        return f"<ClientHealthSnapshot id={self.id!r} health_score={self.health_score!r}>"
