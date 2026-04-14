"""SQLAlchemy models for public intake forms."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, Boolean, Integer, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.db.base import Base


def _uuid():
    return str(uuid.uuid4())


def _utcnow():
    return datetime.now(timezone.utc)


class PublicForm(Base):
    __tablename__ = "public_forms"

    id             = Column(String(36), primary_key=True, default=_uuid)
    name           = Column(String(255), nullable=False)
    description    = Column(Text, nullable=True)
    form_type      = Column(String(20), nullable=False)          # ticket | task
    token          = Column(String(64), nullable=False, unique=True, index=True)
    is_active      = Column(Boolean, default=True)
    target_project_id = Column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    target_group_id   = Column(String(36), nullable=True)
    default_priority  = Column(String(20), default="medium")
    default_category  = Column(String(100), nullable=True)
    fields_config     = Column(Text, default="[]")               # JSON
    success_message   = Column(String(500), nullable=True)
    notify_emails     = Column(Text, default="[]")               # JSON
    submission_count  = Column(Integer, default=0)
    created_by     = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at     = Column(DateTime(timezone=True), default=_utcnow)
    updated_at     = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    submissions    = relationship("PublicFormSubmission", back_populates="form", cascade="all, delete-orphan")


class PublicFormSubmission(Base):
    __tablename__ = "public_form_submissions"

    id                  = Column(String(36), primary_key=True, default=_uuid)
    form_id             = Column(String(36), ForeignKey("public_forms.id", ondelete="CASCADE"), nullable=False, index=True)
    submitter_name      = Column(String(255), nullable=True)
    submitter_email     = Column(String(255), nullable=True)
    subject             = Column(String(500), nullable=False)
    description         = Column(Text, nullable=True)
    priority            = Column(String(20), default="medium")
    category            = Column(String(100), nullable=True)
    extra_fields        = Column(Text, default="{}")             # JSON
    created_entity_id   = Column(String(36), nullable=True)
    created_entity_type = Column(String(20), nullable=True)      # ticket | task
    ip_address          = Column(String(45), nullable=True)
    submitted_at        = Column(DateTime(timezone=True), default=_utcnow)

    form = relationship("PublicForm", back_populates="submissions")
