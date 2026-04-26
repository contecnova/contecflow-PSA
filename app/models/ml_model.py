"""
ml_model.py — Persisted ML model metadata and prediction audit log.

Tables:
  ml_models          — one active model per (org, model_type)
  ml_prediction_logs — per-project prediction history for drift monitoring
"""
import enum
import uuid

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, Float,
    ForeignKey, Integer, LargeBinary, String, Text,
)
from sqlalchemy.sql import func

from app.db.base import Base


class MLModelType(str, enum.Enum):
    overrun = "overrun"   # project cost/schedule overrun classifier


class MLModel(Base):
    """Trained scikit-learn model stored as a joblib blob per organization."""
    __tablename__ = "ml_models"

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    model_type      = Column(Enum(MLModelType), nullable=False, default=MLModelType.overrun)
    version         = Column(Integer, nullable=False, default=1)

    # Training metadata
    trained_at      = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    samples_used    = Column(Integer, nullable=False, default=0)
    accuracy        = Column(Float, nullable=True)   # ROC-AUC on held-out set
    feature_names   = Column(Text, nullable=True)    # JSON array of feature names in order
    is_active       = Column(Boolean, nullable=False, default=True)

    # Serialized model (joblib.dumps output)
    model_bytes     = Column(LargeBinary, nullable=True)


class MLPredictionLog(Base):
    """One row per prediction call — tracks feature drift and model performance."""
    __tablename__ = "ml_prediction_logs"

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    ml_model_id     = Column(String(36), ForeignKey("ml_models.id", ondelete="SET NULL"), nullable=True)
    project_id      = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)

    # Snapshot of features at prediction time
    features_json   = Column(Text, nullable=True)    # JSON: {feature: value}

    cost_overrun_prob    = Column(Float, nullable=True)
    schedule_overrun_prob = Column(Float, nullable=True)
    risk_level          = Column(String(20), nullable=True)   # low | medium | high | critical
    used_heuristic      = Column(Boolean, nullable=False, default=False)

    # Outcome feedback (filled in retrospectively by Celery)
    did_cost_overrun     = Column(Boolean, nullable=True)
    did_schedule_overrun = Column(Boolean, nullable=True)

    predicted_at    = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
