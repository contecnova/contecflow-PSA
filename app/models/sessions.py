from sqlalchemy import Column, String, DateTime, Integer, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.db.base import Base


class UserSession(Base):
    """Sesión activa de un usuario con metadatos de dispositivo, IP y nivel de riesgo."""
    __tablename__ = "user_sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    refresh_token_jti = Column(String(36), nullable=False, unique=True, index=True)

    ip_address = Column(String(64), nullable=True, index=True)
    ip_asn = Column(String(32), nullable=True)
    ip_org = Column(String(255), nullable=True)
    country_code = Column(String(8), nullable=True)
    region = Column(String(120), nullable=True)
    city = Column(String(120), nullable=True)

    user_agent = Column(String(512), nullable=True)
    device_name = Column(String(255), nullable=True)

    risk_score = Column(Integer, nullable=False, default=0)
    risk_level = Column(String(20), nullable=False, default="low")
    risk_reasons = Column(Text, nullable=True)  # JSON list string

    auth_method = Column(String(30), nullable=True)  # password | sso | totp | webauthn | refresh
    last_seen_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    revoke_reason = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", foreign_keys=[user_id])

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    def __repr__(self) -> str:
        return f"<UserSession id={self.id!r} user_id={self.user_id!r}>"
