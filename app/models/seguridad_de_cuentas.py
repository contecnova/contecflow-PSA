"""Políticas de cuenta (migración 199, 23-11-2026).

- `PasswordHistory`: hashes bcrypt de las últimas contraseñas (no reutilizar).
- `TrustedDevice`: dispositivo recordado para no repetir el reto MFA (solo el
  SHA-256 del token; el token vive en una cookie httpOnly).
- `SecurityChangeRequest`: cambio de seguridad pendiente de un segundo
  administrador (separación de funciones).
- `AccessReviewCampaign` / `AccessReviewItem`: recertificación periódica de
  accesos por responsable, con la foto del acceso y la decisión como evidencia.
- `AuditLogPurgePermit`: permiso de un solo uso para que la purga de una empresa
  borre su registro de auditoría (los triggers de `app/db/auditoria_inmutable.py`
  niegan cualquier otro DELETE).

Documentado en docs/seguridad/politicas_de_cuenta.md.
"""
import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class PasswordHistory(Base):
    """Una contraseña anterior del usuario (solo el hash)."""
    __tablename__ = "password_history"

    id = Column(String(36), primary_key=True, default=_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TrustedDevice(Base):
    """Dispositivo en el que el usuario pidió no repetir el MFA durante N días."""
    __tablename__ = "trusted_devices"

    id = Column(String(36), primary_key=True, default=_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    device_name = Column(String(255), nullable=True)
    ip_address = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    revoke_reason = Column(String(120), nullable=True)


class SecurityChangeRequest(Base):
    """Cambio de seguridad que aplica un SEGUNDO administrador (`SECURITY_SOD_TWO_ADMINS`)."""
    __tablename__ = "security_change_requests"

    id = Column(String(36), primary_key=True, default=_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = Column(String(40), nullable=False)          # policy | mfa_reset
    target_user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    payload = Column(Text, nullable=True)              # JSON del cambio pedido
    reason = Column(String(500), nullable=True)
    status = Column(String(20), nullable=False, default="pending", index=True)  # pending|applied|rejected|expired
    requested_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    requested_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    decided_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    decision_comment = Column(String(500), nullable=True)


class AccessReviewCampaign(Base):
    """Campaña de recertificación de accesos (ISO 27001 A.5.18)."""
    __tablename__ = "access_review_campaigns"

    id = Column(String(36), primary_key=True, default=_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    status = Column(String(20), nullable=False, default="open", index=True)   # open | closed
    due_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    closed_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)

    items = relationship("AccessReviewItem", back_populates="campaign", cascade="all, delete-orphan",
                         passive_deletes=True)


class AccessReviewItem(Base):
    """El acceso de una persona, revisado por su responsable."""
    __tablename__ = "access_review_items"

    id = Column(String(36), primary_key=True, default=_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    campaign_id = Column(String(36), ForeignKey("access_review_campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    reviewer_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    snapshot = Column(Text, nullable=True)            # JSON: rol, capacidades, MFA, último acceso...
    decision = Column(String(20), nullable=False, default="pending")   # pending | keep | revoke | modify
    comment = Column(String(1000), nullable=True)     # evidencia de la decisión
    decided_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    applied_at = Column(DateTime(timezone=True), nullable=True)

    campaign = relationship("AccessReviewCampaign", back_populates="items")

    __table_args__ = (Index("ix_access_review_items_reviewer_decision", "reviewer_id", "decision"),)


class AuditLogPurgePermit(Base):
    """Permiso para que la purga de una empresa borre su registro de auditoría.

    Es infraestructura de la purga (`baja_de_empresa_service.purgar`), que lo
    abre y lo cierra con SQL directo en la misma transacción.
    """
    __tablename__ = "audit_log_purge_permits"

    organization_id = Column(String(36), primary_key=True)
    reason = Column(String(200), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    uses = Column(Integer, nullable=False, default=0)
    active = Column(Boolean, nullable=False, default=True)
