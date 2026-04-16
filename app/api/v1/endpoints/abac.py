"""
ABAC (Attribute-Based Access Control) API endpoints for policy and attribute management.
"""
from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.core.deps import get_db, get_current_user
from app.core.security import verify_admin_or_governance_role
from app.models.user import User
from app.models.abac import UserAttribute, ABACPolicy, AttributeDefinition
from app.services.abac import ABACService, DEFAULT_ABAC_ATTRIBUTES
from pydantic import BaseModel, Field
import uuid


# ============================================================================
# Pydantic Schemas
# ============================================================================

class AttributeDefinitionSchema(BaseModel):
    """Schema for attribute definition."""
    id: str
    attribute_key: str
    attribute_type: str
    description: Optional[str]
    possible_values: Optional[List[Any]]
    operators: List[str]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class UserAttributeAssignSchema(BaseModel):
    """Schema for assigning attributes to users."""
    attribute_key: str = Field(..., description="e.g., 'project_ids', 'region'")
    attribute_value: Any = Field(..., description="Value: string, list, or structured data")
    reason: Optional[str] = Field(None, description="Audit reason")
    expires_at: Optional[datetime] = Field(None, description="When attribute expires")


class UserAttributeSchema(BaseModel):
    """Schema for user attribute."""
    id: str
    user_id: str
    attribute_key: str
    attribute_value: Any
    expires_at: Optional[datetime]
    reason: Optional[str]
    created_at: datetime
    assigned_by: Optional[str]

    class Config:
        from_attributes = True


class ABACRuleSchema(BaseModel):
    """Schema for ABAC policy rule condition."""
    attribute: str = Field(..., description="Attribute key to match")
    operator: str = Field(
        ...,
        description="Operator: equals, in, not_in, contains, regex, gte, lte, is_empty, etc."
    )
    value: Any = Field(..., description="Value to match against")


class ABACPolicyCreateSchema(BaseModel):
    """Schema for creating ABAC policy."""
    policy_name: str = Field(..., description="Human-readable policy name")
    description: Optional[str] = None
    effect: str = Field("allow", description="'allow' or 'deny'")
    rules: List[ABACRuleSchema] = Field(..., description="Conditions that must match")
    resource_types: Optional[List[str]] = Field(
        None,
        description="If specified, policy applies only to these resources (e.g., [\"timesheets\", \"expenses\"])"
    )
    applicable_roles: Optional[List[str]] = Field(
        None,
        description="If specified, policy applies only to users with these roles"
    )
    subject_users: Optional[List[str]] = Field(
        None,
        description="If specified, policy applies only to these users"
    )
    priority: int = Field(50, description="0-100, higher = evaluated first")
    expires_at: Optional[datetime] = Field(None, description="When policy expires")


class ABACPolicySchema(BaseModel):
    """Schema for ABAC policy."""
    id: str
    policy_name: str
    description: Optional[str]
    effect: str
    rules: List[Dict[str, Any]]
    resource_types: List[str]
    applicable_roles: List[str]
    subject_users: List[str]
    priority: int
    starts_at: Optional[datetime]
    expires_at: Optional[datetime]
    is_active: bool
    created_at: datetime
    created_by: Optional[str]

    class Config:
        from_attributes = True


class AccessEvaluationRequestSchema(BaseModel):
    """Schema for evaluating access decision."""
    resource_type: Optional[str] = Field(None, description="Type of resource being accessed")
    resource_id: Optional[str] = Field(None, description="ID of resource being accessed")
    action: str = Field("read", description="Action being performed")
    context: Optional[Dict[str, Any]] = Field(None, description="Additional context attributes")


class AccessEvaluationResponseSchema(BaseModel):
    """Schema for access evaluation result."""
    decision: bool = Field(..., description="True if access is allowed")
    matched_policies: List[str] = Field(..., description="Policies that matched")
    details: Dict[str, Any] = Field(..., description="Evaluation details")


# ============================================================================
# Router
# ============================================================================

router = APIRouter(prefix="/abac", tags=["ABAC"])


# ============================================================================
# Attribute Definition Management
# ============================================================================

@router.get("/attribute-definitions")
def list_attribute_definitions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    active_only: bool = Query(True),
) -> List[AttributeDefinitionSchema]:
    """List available attribute definitions for org."""
    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="User organization not set")
    service = ABACService(db, org_id)
    definitions = service.list_attribute_definitions(active_only=active_only)
    return [AttributeDefinitionSchema.model_validate(d) for d in definitions]


@router.post("/attribute-definitions")
def create_attribute_definition(
    schema: AttributeDefinitionSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create new attribute definition (admin only)."""
    verify_admin_or_governance_role(current_user)
    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="User organization not set")

    service = ABACService(db, org_id)
    attr_def = service.create_attribute_definition(
        attribute_key=schema.attribute_key,
        attribute_type=schema.attribute_type,
        operators=schema.operators,
        description=schema.description,
        possible_values=schema.possible_values,
        created_by=current_user.id,
    )
    return AttributeDefinitionSchema.model_validate(attr_def)


@router.post("/attribute-definitions/initialize")
def initialize_default_attributes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Initialize common PSA attributes. Safe to call multiple times (idempotent)."""
    verify_admin_or_governance_role(current_user)
    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="User organization not set")

    service = ABACService(db, org_id)
    existing = service.list_attribute_definitions(active_only=False)
    existing_keys = {a.attribute_key for a in existing}

    created = []
    for attr in DEFAULT_ABAC_ATTRIBUTES:
        if attr["attribute_key"] not in existing_keys:
            attr_def = service.create_attribute_definition(
                attribute_key=attr["attribute_key"],
                attribute_type=attr["attribute_type"],
                operators=attr["operators"],
                description=attr.get("description"),
                possible_values=attr.get("possible_values"),
                created_by=current_user.id,
            )
            created.append(AttributeDefinitionSchema.model_validate(attr_def))

    return {"created": len(created), "attributes": created}


# ============================================================================
# User Attribute Management
# ============================================================================

@router.get("/users/{user_id}/attributes")
def get_user_attributes(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Get all attributes for a user (non-expired)."""
    # Check permission: user can view their own, admins can view others
    if current_user.id != user_id and "admin" not in [r.name for r in current_user.roles]:
        raise HTTPException(status_code=403, detail="Cannot view other user's attributes")
    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="User organization not set")

    service = ABACService(db, org_id)
    attrs = service.get_user_attributes(user_id)
    return {"user_id": user_id, "attributes": attrs}


@router.post("/users/{user_id}/attributes")
def assign_user_attribute(
    user_id: str,
    schema: UserAttributeAssignSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserAttributeSchema:
    """Assign an attribute to a user (admin/governance only)."""
    verify_admin_or_governance_role(current_user)
    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="User organization not set")

    service = ABACService(db, org_id)
    attr = service.assign_user_attribute(
        user_id=user_id,
        attribute_key=schema.attribute_key,
        attribute_value=schema.attribute_value,
        assigned_by=current_user.id,
        reason=schema.reason,
        expires_at=schema.expires_at,
    )
    return UserAttributeSchema.model_validate(attr)


@router.delete("/users/{user_id}/attributes/{attribute_key}")
def revoke_user_attribute(
    user_id: str,
    attribute_key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Revoke an attribute from a user (admin/governance only)."""
    verify_admin_or_governance_role(current_user)
    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="User organization not set")

    service = ABACService(db, org_id)
    count = service.revoke_user_attribute(user_id, attribute_key)
    return {"revoked": count}


# ============================================================================
# ABAC Policy Management
# ============================================================================

@router.get("/policies")
def list_policies(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    active_only: bool = Query(True),
) -> List[ABACPolicySchema]:
    """List ABAC policies for org."""
    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="User organization not set")
    service = ABACService(db, org_id)
    policies = service.list_policies(active_only=active_only)
    return [ABACPolicySchema.model_validate(p) for p in policies]


@router.post("/policies")
def create_policy(
    schema: ABACPolicyCreateSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ABACPolicySchema:
    """Create new ABAC policy (admin/governance only)."""
    verify_admin_or_governance_role(current_user)
    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="User organization not set")

    rules = [r.dict() for r in schema.rules]
    service = ABACService(db, org_id)
    policy = service.create_policy(
        policy_name=schema.policy_name,
        description=schema.description,
        effect=schema.effect,
        rules=rules,
        resource_types=schema.resource_types,
        applicable_roles=schema.applicable_roles,
        subject_users=schema.subject_users,
        priority=schema.priority,
        expires_at=schema.expires_at,
        created_by=current_user.id,
    )
    return ABACPolicySchema.model_validate(policy)


@router.get("/policies/{policy_id}")
def get_policy(
    policy_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ABACPolicySchema:
    """Get a specific policy."""
    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="User organization not set")
    service = ABACService(db, org_id)
    policy = service.get_policy_by_id(policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    return ABACPolicySchema.model_validate(policy)


@router.put("/policies/{policy_id}")
def update_policy(
    policy_id: str,
    schema: ABACPolicyCreateSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ABACPolicySchema:
    """Update an ABAC policy (admin/governance only)."""
    verify_admin_or_governance_role(current_user)
    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="User organization not set")

    rules = [r.dict() for r in schema.rules]
    service = ABACService(db, org_id)
    policy = service.update_policy(
        policy_id,
        policy_name=schema.policy_name,
        description=schema.description,
        effect=schema.effect,
        rules=rules,
        resource_types=schema.resource_types,
        applicable_roles=schema.applicable_roles,
        subject_users=schema.subject_users,
        priority=schema.priority,
        expires_at=schema.expires_at,
    )
    return ABACPolicySchema.model_validate(policy)


@router.delete("/policies/{policy_id}")
def delete_policy(
    policy_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete (soft) an ABAC policy (admin/governance only)."""
    verify_admin_or_governance_role(current_user)
    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="User organization not set")

    service = ABACService(db, org_id)
    service.delete_policy(policy_id)
    return {"deleted": True}


# ============================================================================
# Access Evaluation
# ============================================================================

@router.post("/evaluate")
def evaluate_access(
    schema: AccessEvaluationRequestSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AccessEvaluationResponseSchema:
    """
    Evaluate if current user can access a resource based on ABAC policies.

    This endpoint is typically called by service code to make access decisions,
    but can also be used for testing/debugging.
    """
    user_roles = [r.name for r in current_user.roles]
    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="User organization not set")
    service = ABACService(db, org_id)

    decision, matched_policies, details = service.evaluate_access(
        user_id=current_user.id,
        user_roles=user_roles,
        resource_type=schema.resource_type,
        resource_id=schema.resource_id,
        action=schema.action,
        context=schema.context,
    )

    # Audit the decision
    service.audit_access_decision(
        user_id=current_user.id,
        decision=decision,
        matched_policies=matched_policies,
        resource_type=schema.resource_type,
        resource_id=schema.resource_id,
        details=details,
    )

    return AccessEvaluationResponseSchema(
        decision=decision,
        matched_policies=matched_policies,
        details=details,
    )


@router.post("/evaluate/{user_id}")
def evaluate_access_for_user(
    user_id: str,
    schema: AccessEvaluationRequestSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AccessEvaluationResponseSchema:
    """
    Evaluate access for a specific user (admin/governance only).
    Useful for testing and debugging access policies.
    """
    verify_admin_or_governance_role(current_user)
    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="User organization not set")

    service = ABACService(db, org_id)
    user = service.get_user_by_id_and_org(user_id)
    user_roles = [r.name for r in user.roles]
    decision, matched_policies, details = service.evaluate_access(
        user_id=user.id,
        user_roles=user_roles,
        resource_type=schema.resource_type,
        resource_id=schema.resource_id,
        action=schema.action,
        context=schema.context,
    )

    return AccessEvaluationResponseSchema(
        decision=decision,
        matched_policies=matched_policies,
        details=details,
    )


@router.get("/audit-log")
def get_audit_log(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    user_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Get audit log of ABAC decisions (admin/governance only)."""
    verify_admin_or_governance_role(current_user)
    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="User organization not set")

    service = ABACService(db, org_id)
    result = service.list_audit_log(user_id=user_id, limit=limit, offset=offset)
    logs = result["logs"]

    return {
        "total": result["total"],
        "offset": offset,
        "limit": limit,
        "logs": [
            {
                "id": log.id,
                "user_id": log.user_id,
                "action": log.action,
                "result": log.result,
                "resource_type": log.resource_type,
                "resource_id": log.resource_id,
                "created_at": log.created_at,
            }
            for log in logs
        ],
    }
