"""Módulo de formación y certificaciones."""
import uuid
import enum
from sqlalchemy import Column, String, Text, Float, Boolean, ForeignKey, Date
from sqlalchemy import DateTime, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base


class CourseStatus(str, enum.Enum):
    planned    = "planned"
    in_progress = "in_progress"
    completed  = "completed"
    cancelled  = "cancelled"


class Course(Base):
    """Curso o formación del catálogo."""
    __tablename__ = "training_courses"
    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    title       = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    provider    = Column(String(200), nullable=True)
    category    = Column(String(100), nullable=True)   # técnico, soft, idioma…
    duration_h  = Column(Float, nullable=True)
    url         = Column(String(500), nullable=True)
    cost        = Column(Float, nullable=True)
    is_active   = Column(Boolean, default=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    enrollments = relationship("CourseEnrollment", back_populates="course",
                               cascade="all, delete-orphan")


class CourseEnrollment(Base):
    """Inscripción de un usuario a un curso."""
    __tablename__ = "training_enrollments"
    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    course_id   = Column(String(36), ForeignKey("training_courses.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    user_id     = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    status      = Column(Enum(CourseStatus), default=CourseStatus.planned)
    start_date  = Column(Date, nullable=True)
    end_date    = Column(Date, nullable=True)
    score       = Column(Float, nullable=True)
    notes       = Column(Text, nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    course      = relationship("Course", back_populates="enrollments")
    user        = relationship("User", foreign_keys=[user_id])


class Certification(Base):
    """Certificación obtenida por un usuario."""
    __tablename__ = "user_certifications"
    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    user_id     = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    name        = Column(String(300), nullable=False)
    issuer      = Column(String(200), nullable=True)
    cert_id     = Column(String(200), nullable=True)   # número/ID del certificado
    obtained_at = Column(Date, nullable=True)
    expires_at  = Column(Date, nullable=True)
    url         = Column(String(500), nullable=True)
    notes       = Column(Text, nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    user        = relationship("User", foreign_keys=[user_id])
