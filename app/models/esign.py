"""
E-firma (electronic signature) model.

Supports DocuSign and Adobe Sign via their REST APIs.
NexusPM stores envelope metadata and tracks signer completion.
The provider does all signing logic; we only store the result.
"""

import enum
from app.core.timeutil import utcnow
from sqlalchemy import Column, Integer, String, Text, Enum as SAEnum, DateTime, ForeignKey, Boolean, JSON
from sqlalchemy.orm import relationship
from app.db.base import Base


class ESignProvider(str, enum.Enum):
    docusign   = "docusign"
    adobe_sign = "adobe_sign"
    manual     = "manual"   # placeholder when no integration is configured


class ESignStatus(str, enum.Enum):
    draft     = "draft"      # created but not yet sent
    sent      = "sent"       # envelope sent to signers
    delivered = "delivered"  # at least one signer viewed it
    completed = "completed"  # all signers signed
    declined  = "declined"   # at least one signer declined
    voided    = "voided"     # cancelled
    error     = "error"      # provider error


class ESignEnvelope(Base):
    """An e-sign envelope linked to a document."""
    __tablename__ = "esign_envelopes"

    id              = Column(Integer, primary_key=True, index=True)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    document_id     = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by_id   = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    provider        = Column(SAEnum(ESignProvider), default=ESignProvider.docusign)
    provider_envelope_id = Column(String(256), nullable=True, unique=True)  # DocuSign/Adobe envelope ID
    subject         = Column(String(512))
    message         = Column(Text)
    status          = Column(SAEnum(ESignStatus), default=ESignStatus.draft)
    signing_url     = Column(String(1024), nullable=True)  # embedded signing URL
    completed_pdf_path = Column(String(1024), nullable=True)  # path to signed PDF
    provider_meta   = Column(JSON, nullable=True)  # raw provider metadata
    sent_at         = Column(DateTime, nullable=True)
    completed_at    = Column(DateTime, nullable=True)
    expires_at      = Column(DateTime, nullable=True)
    created_at      = Column(DateTime, default=utcnow)
    updated_at      = Column(DateTime, default=utcnow, onupdate=utcnow)
    is_active       = Column(Boolean, default=True, nullable=False, server_default="1", index=True)  # audit #36 soft-delete

    document    = relationship("Document",       back_populates=None, foreign_keys=[document_id])
    created_by  = relationship("User",           back_populates=None, foreign_keys=[created_by_id])
    signers     = relationship("ESignSigner",    back_populates="envelope", cascade="all, delete-orphan")


class ESignSigner(Base):
    """A signer on an e-sign envelope."""
    __tablename__ = "esign_signers"

    id              = Column(Integer, primary_key=True, index=True)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    envelope_id     = Column(Integer, ForeignKey("esign_envelopes.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id         = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    name            = Column(String(256), nullable=False)
    email           = Column(String(256), nullable=False)
    routing_order   = Column(Integer, default=1)   # signing order (sequential flow)
    signed          = Column(Boolean, default=False)
    signed_at       = Column(DateTime, nullable=True)
    signing_url     = Column(String(1024), nullable=True)  # per-signer embedded URL
    provider_recipient_id = Column(String(256), nullable=True)
    created_at      = Column(DateTime, default=utcnow)

    envelope = relationship("ESignEnvelope", back_populates="signers")
    user     = relationship("User", back_populates=None, foreign_keys=[user_id])
