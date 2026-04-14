"""
AI Governance DB models:
- AIGuardrailPolicyModel: per-org configurable guardrail rule
- AIGuardrailAuditLog:    immutable audit of every guardrail evaluation
"""
import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime, Text, JSON,
    ForeignKey, Index,
)
from sqlalchemy.orm import relationship
from app.db.base import Base


class AIGuardrailPolicyModel(Base):
    """
    Guardrail policy: defines what to do when PII / forbidden content is
    found in a prompt or AI output for a given org / role / module combination.
    """
    __tablename__ = "ai_guardrail_policies"

    id                  = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id              = Column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    name                = Column(String(128), nullable=False)
    description         = Column(Text, nullable=True)

    # Scope selectors
    applies_to_modules  = Column(JSON, default=list)  # ["nexusassist", "*"]
    applies_to_roles    = Column(JSON, default=list)  # ["employee", "pm", "*"]
    scope               = Column(String(16), default="both")  # prompt | output | both

    # Action
    action              = Column(String(16), default="redact")  # block | redact | warn | log
    pii_entity_types    = Column(JSON, default=list)            # [] = all PII types
    redact_strategy     = Column(String(16), default="mask")    # mask | hash | partial | remove
    forbidden_keywords  = Column(JSON, default=list)            # lowercase exact/substring

    # Limits
    max_prompt_tokens   = Column(Integer, default=0)  # 0 = unlimited

    # Control
    is_active           = Column(Boolean, default=True, index=True)
    priority            = Column(Integer, default=0)   # higher = evaluated first
    created_by          = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at          = Column(DateTime, default=datetime.utcnow)
    updated_at          = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_guardrail_org_active", "org_id", "is_active"),
    )

    organization = relationship("Organization", backref="guardrail_policies")
    creator      = relationship("User", foreign_keys=[created_by])


class AIGuardrailAuditLog(Base):
    """
    Immutable record of every guardrail evaluation — satisfies audit/compliance.

    Never updated; only inserted.
    """
    __tablename__ = "ai_guardrail_audit_logs"

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id          = Column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    user_id         = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    module          = Column(String(64),  nullable=False, index=True)
    scope           = Column(String(16),  nullable=False)      # prompt | output
    policy_id       = Column(String(36),  ForeignKey("ai_guardrail_policies.id"), nullable=True, index=True)
    request_id      = Column(String(64),  nullable=True, index=True)  # correlation ID

    action_taken    = Column(String(16),  nullable=False)      # none | redacted | blocked | warned
    pii_types_found = Column(JSON,        default=list)         # ["email", "phone_es"]
    was_blocked     = Column(Boolean,     default=False, index=True)
    blocked_reason  = Column(String(256), nullable=True)
    original_length = Column(Integer,     default=0)            # char count (not stored content)
    warnings        = Column(JSON,        default=list)

    evaluated_at    = Column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index("idx_guardrail_audit_org_ts",  "org_id", "evaluated_at"),
        Index("idx_guardrail_audit_blocked", "org_id", "was_blocked"),
        Index("idx_guardrail_audit_user",    "user_id", "evaluated_at"),
    )

    organization = relationship("Organization", backref="guardrail_audit_logs")
    user         = relationship("User", foreign_keys=[user_id])
    policy       = relationship("AIGuardrailPolicyModel", foreign_keys=[policy_id])
