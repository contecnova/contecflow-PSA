"""SQLAlchemy models for the Developer Portal (OAuth2 apps)."""
import uuid
import secrets
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.db.base import Base


def _uuid():
    return str(uuid.uuid4())


def _utcnow():
    return datetime.now(timezone.utc)


class OAuthApp(Base):
    __tablename__ = "oauth_apps"

    id                  = Column(String(36), primary_key=True, default=_uuid)
    name                = Column(String(255), nullable=False)
    description         = Column(Text, nullable=True)
    homepage_url        = Column(String(500), nullable=True)
    client_id           = Column(String(64), nullable=False, unique=True, index=True)
    client_secret_hash  = Column(String(255), nullable=False)  # bcrypt hash
    redirect_uris       = Column(Text, nullable=False, default="[]")   # JSON
    scopes              = Column(Text, nullable=False, default='["read"]')  # JSON
    is_active           = Column(Boolean, default=True)
    is_first_party      = Column(Boolean, default=False)
    owner_id            = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at          = Column(DateTime(timezone=True), default=_utcnow)
    updated_at          = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    tokens = relationship("OAuthToken", back_populates="app", cascade="all, delete-orphan")


class OAuthToken(Base):
    __tablename__ = "oauth_tokens"

    id                  = Column(String(36), primary_key=True, default=_uuid)
    app_id              = Column(String(36), ForeignKey("oauth_apps.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id             = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    access_token_hash   = Column(String(255), nullable=False)
    refresh_token_hash  = Column(String(255), nullable=True)
    scopes              = Column(Text, nullable=False, default='["read"]')
    expires_at          = Column(DateTime(timezone=True), nullable=True)
    revoked             = Column(Boolean, default=False)
    created_at          = Column(DateTime(timezone=True), default=_utcnow)

    app = relationship("OAuthApp", back_populates="tokens")
