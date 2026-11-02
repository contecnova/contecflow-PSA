"""service_desk.knowledge models — split from the former 1385-LOC god-file."""

from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Boolean, Integer, Enum, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.db.base import Base


from app.models.service_desk._enums import KBStatus

class KBArticle(Base):
    __tablename__ = "sd_kb_articles"
    __table_args__ = (UniqueConstraint("organization_id", "number", name="uq_sd_kb_articles_org_number"),)

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    number = Column(String(20), nullable=False)
    title = Column(String(500), nullable=False)
    body = Column(Text, nullable=False)
    summary = Column(String(500), nullable=True)
    status = Column(Enum(KBStatus), default=KBStatus.draft, index=True)

    category_id = Column(String(36), ForeignKey("sd_service_categories.id"), nullable=True)
    tags = Column(String(500), nullable=True)
    is_public = Column(Boolean, default=True)

    created_from_ticket_id = Column(String(36), nullable=True)
    service_item_id = Column(String(36), ForeignKey("sd_service_items.id"), nullable=True)

    view_count = Column(Integer, default=0)
    # Veces que un cliente dijo «esto me lo resuelve» antes de abrir un ticket.
    deflection_count = Column(Integer, default=0, nullable=False)
    # Vector del titulo y el texto para la busqueda semantica (JSON). Se
    # calcula al guardar: antes se recalculaba el de cada articulo en cada
    # sugerencia.
    embedding = Column(Text, nullable=True)
    review_comment = Column(Text, nullable=True)
    helpful_count = Column(Integer, default=0)
    not_helpful_count = Column(Integer, default=0)

    author_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    reviewer_id = Column(String(36), ForeignKey("users.id"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    published_at = Column(DateTime(timezone=True), nullable=True)

    category = relationship("ServiceCategory")
    author = relationship("User", foreign_keys=[author_id])
    reviewer = relationship("User", foreign_keys=[reviewer_id])
    versions = relationship(
        "KBArticleVersion",
        back_populates="article",
        cascade="all, delete-orphan",
        order_by="KBArticleVersion.version.desc()",
    )

class KBArticleVersion(Base):
    """Immutable KB snapshot used for audit trail and rollback."""
    __tablename__ = "sd_kb_article_versions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    article_id = Column(String(36), ForeignKey("sd_kb_articles.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    title = Column(String(500), nullable=False)
    body = Column(Text, nullable=False)
    summary = Column(String(500), nullable=True)
    tags = Column(String(500), nullable=True)
    status = Column(Enum(KBStatus), default=KBStatus.draft)
    change_note = Column(String(255), nullable=True)
    changed_by_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    article = relationship("KBArticle", back_populates="versions")
    changed_by = relationship("User", foreign_keys=[changed_by_user_id])

class Announcement(Base):
    __tablename__ = "sd_announcements"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    type = Column(String(20), default="info")
    is_active = Column(Boolean, default=True)
    show_to_clients = Column(Boolean, default=True)
    starts_at = Column(DateTime(timezone=True), nullable=True)
    ends_at = Column(DateTime(timezone=True), nullable=True)

    ci_id = Column(String(36), ForeignKey("sd_configuration_items.id"), nullable=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    ci = relationship("ConfigurationItem")
    creator = relationship("User", foreign_keys=[created_by])
