"""Proyectos — planificador, hub y vistas (rev. 173, 16-11-2026).

  · EvmSnapshot: un punto diario de la curva S de cada proyecto (lo escribe el
    worker, `app.worker.guardar_puntos_de_curva_s`). Antes el valor ganado solo
    existía «hoy»: no había histórico con el que dibujar la curva.
"""
import uuid

from sqlalchemy import Column, Date, DateTime, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.sql import func

from app.db.base import Base


class EvmSnapshot(Base):
    __tablename__ = "evm_snapshots"
    __table_args__ = (UniqueConstraint("project_id", "snapshot_date", name="uq_evm_snapshot_dia"),)

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    snapshot_date = Column(Date, nullable=False, index=True)
    baseline_id = Column(String(36), nullable=True)      # la línea base vigente ese día (sin FK: puede borrarse)
    bac = Column(Float, nullable=True)
    pv = Column(Float, nullable=True)
    ev = Column(Float, nullable=True)
    ac = Column(Float, nullable=True)
    cpi = Column(Float, nullable=True)
    spi = Column(Float, nullable=True)
    pct_complete = Column(Float, nullable=True)
    pct_planned = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
