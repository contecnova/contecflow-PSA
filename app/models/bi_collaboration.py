from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class DashboardComment(Base):
    __tablename__ = "dashboard_comments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    dashboard_key = Column(String(120), nullable=False, index=True)
    widget_id = Column(String(120), nullable=False, index=True)
    message = Column(Text, nullable=False)
    author_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    author_name = Column(String(255), nullable=True)
    resolved = Column(Boolean, nullable=False, server_default="false")
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    author = relationship("User", foreign_keys=[author_id])


class DashboardVersion(Base):
    __tablename__ = "dashboard_versions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    dashboard_key = Column(String(120), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    config = Column(Text, nullable=False)
    change_log = Column(String(500), nullable=True)
    created_by_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_by_name = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("organization_id", "dashboard_key", "version", name="uq_dashboard_version_org_key_ver"),
    )

    created_by = relationship("User", foreign_keys=[created_by_id])


class DashboardShare(Base):
    __tablename__ = "dashboard_shares"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    dashboard_key = Column(String(120), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    user_name = Column(String(255), nullable=True)
    permission = Column(String(20), nullable=False, index=True)
    shared_by_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    shared_by_name = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("organization_id", "dashboard_key", "user_id", name="uq_dashboard_share_org_key_user"),
    )

    shared_by = relationship("User", foreign_keys=[shared_by_id])
    user = relationship("User", foreign_keys=[user_id])


class DashboardNotification(Base):
    __tablename__ = "dashboard_notifications"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    dashboard_key = Column(String(120), nullable=False, index=True)
    event_type = Column(String(50), nullable=False, index=True)
    recipient_user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    payload_json = Column(Text, nullable=False)
    is_read = Column(Boolean, nullable=False, server_default="false")
    read_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    recipient_user = relationship("User", foreign_keys=[recipient_user_id])
