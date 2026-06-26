"""
ABAC (Attribute-Based Access Control) models for fine-grained authorization.

ABAC extends RBAC by adding attribute-based rules that further restrict access
based on project, client, region, data classification, team, and other context.
"""
from datetime import datetime
from app.core.timeutil import utcnow
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, JSON, Boolean, Text, Index
from sqlalchemy.orm import relationship
from app.db.base import Base


class AttributeDefinition(Base):
    """Defines available attributes for ABAC policies."""
    __tablename__ = "abac_attribute_definitions"

    id = Column(String(36), primary_key=True)
    org_id = Column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    attribute_key = Column(String(128), nullable=False)  # e.g., "project_id", "region", "data_classification"
    attribute_type = Column(String(32), nullable=False)  # "string", "list", "enum", "integer", "date"
    description = Column(Text, nullable=True)
    possible_values = Column(JSON, nullable=True)  # For enum type: ["internal", "confidential", "public"]
    operators = Column(JSON, nullable=False)  # ["equals", "in", "contains", "gte", "lte", "regex"]
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)

    __table_args__ = (
        Index("idx_attr_def_org_key", "org_id", "attribute_key"),
    )

    # Relationships
    organization = relationship("Organization", backref="abac_attributes")
    creator = relationship("User", foreign_keys=[created_by])


class UserAttribute(Base):
    """Stores user attribute values for ABAC policy evaluation."""
    __tablename__ = "user_attributes"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    org_id = Column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    attribute_key = Column(String(128), nullable=False)  # e.g., "project_ids", "region"
    attribute_value = Column(JSON, nullable=False)  # Can be string, list, or structured data
    expires_at = Column(DateTime(timezone=True), nullable=True)  # Temporal attribute restrictions
    reason = Column(Text, nullable=True)  # Audit trail
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    assigned_by = Column(String(36), ForeignKey("users.id"), nullable=True)

    __table_args__ = (
        Index("idx_user_attr_user_org", "user_id", "org_id"),
        Index("idx_user_attr_key", "attribute_key"),
    )

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    organization = relationship("Organization", backref="user_attributes")
    assigner = relationship("User", foreign_keys=[assigned_by])


class ABACPolicy(Base):
    """ABAC policy: rules that govern fine-grained access based on attributes."""
    __tablename__ = "abac_policies"

    id = Column(String(36), primary_key=True)
    org_id = Column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    policy_name = Column(String(256), nullable=False)  # e.g., "Project Manager: Q2 Projects"
    description = Column(Text, nullable=True)

    # Policy effect: "allow" or "deny"
    effect = Column(String(10), default="allow", nullable=False)  # "allow" | "deny"

    # Rules: list of attribute conditions
    # Example:
    # [
    #   {"attribute": "project_id", "operator": "in", "value": ["proj-1", "proj-2"]},
    #   {"attribute": "team_id", "operator": "equals", "value": "team-1"},
    #   {"attribute": "data_classification", "operator": "gte", "value": "internal"}
    # ]
    rules = Column(JSON, nullable=False)

    # What resources this policy applies to (e.g., ["timesheets", "expenses", "documents"])
    # Empty list = applies to all resources
    resource_types = Column(JSON, default=list)

    # Which roles this policy applies to (e.g., ["manager", "lead", "admin"])
    # Empty list = applies to all roles
    applicable_roles = Column(JSON, default=list)

    # Who is subject to this policy (user_ids)
    subject_users = Column(JSON, default=list)  # If empty, applies to users with matching roles

    # Priority: higher priority policies evaluated first (0-100)
    priority = Column(Integer, default=50)

    # Temporal restrictions
    starts_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)

    # Audit trail
    last_evaluated_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_policy_org_active", "org_id", "is_active"),
        Index("idx_policy_priority", "priority"),
    )

    # Relationships
    organization = relationship("Organization", backref="abac_policies")
    creator = relationship("User", foreign_keys=[created_by])


class PolicyAudit(Base):
    """Audit trail for ABAC policy evaluations and changes."""
    __tablename__ = "policy_audit_log"

    id = Column(String(36), primary_key=True)
    org_id = Column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    policy_id = Column(String(36), ForeignKey("abac_policies.id"), nullable=True, index=True)

    action = Column(String(64), nullable=False)  # "policy_created", "policy_updated", "policy_deleted", "access_denied", "access_allowed"
    resource_type = Column(String(128), nullable=True)
    resource_id = Column(String(128), nullable=True)

    # Policy evaluation result
    result = Column(String(10), nullable=True)  # "allow", "deny"
    matched_policies = Column(JSON, nullable=True)  # List of policy IDs that matched
    evaluation_context = Column(JSON, nullable=True)  # User attributes and request context

    detail = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, index=True)

    __table_args__ = (
        Index("idx_audit_org_user", "org_id", "user_id"),
        Index("idx_audit_policy", "policy_id"),
        Index("idx_audit_action", "action"),
    )

    # Relationships
    organization = relationship("Organization", backref="policy_audits")
    user = relationship("User")
    policy = relationship("ABACPolicy")
