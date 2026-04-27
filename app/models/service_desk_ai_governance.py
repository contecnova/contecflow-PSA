"""Service Desk AI governance and drift monitoring models."""
from __future__ import annotations

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from app.db.base import Base


class SDAIEvaluationRun(Base):
    __tablename__ = "sd_ai_evaluation_runs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    model_name = Column(String(120), nullable=False)
    task_type = Column(String(50), nullable=False)  # triage|routing|auto_resolution
    dataset_name = Column(String(120), nullable=True)
    status = Column(String(20), default="completed")
    score = Column(String(20), nullable=True)
    metrics_json = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SDAIDriftSnapshot(Base):
    __tablename__ = "sd_ai_drift_snapshots"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    model_name = Column(String(120), nullable=False)
    feature_set = Column(String(120), nullable=False, default="default")
    drift_score = Column(Integer, nullable=False, default=0)  # 0-100
    status = Column(String(20), default="ok")               # ok|warning|critical
    details_json = Column(Text, nullable=True)
    measured_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
