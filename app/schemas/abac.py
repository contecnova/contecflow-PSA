from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class AttributeDefinitionSchema(BaseModel):
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
    attribute_key: str = Field(..., description="e.g., 'project_ids', 'region'")
    attribute_value: Any = Field(..., description="Value: string, list, or structured data")
    reason: Optional[str] = Field(None, description="Audit reason")
    expires_at: Optional[datetime] = Field(None, description="When attribute expires")

class UserAttributeSchema(BaseModel):
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
    attribute: str = Field(..., description="Attribute key to match")
    operator: str = Field(
        ...,
        description="Operator: equals, in, not_in, contains, regex, gte, lte, is_empty, etc."
    )
    value: Any = Field(..., description="Value to match against")

class ABACPolicyCreateSchema(BaseModel):
    policy_name: str = Field(..., description="Human-readable policy name")
    description: Optional[str] = None
    effect: str = Field("allow", description="'allow' or 'deny'")
    rules: List[ABACRuleSchema] = Field(..., description="Conditions that must match")
    resource_types: Optional[List[str]] = Field(
        None,
        description="If specified, policy applies only to these resources (e.g., ['timesheets', 'expenses'])"
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
    resource_type: Optional[str] = Field(None, description="Type of resource being accessed")
    resource_id: Optional[str] = Field(None, description="ID of resource being accessed")
    action: str = Field("read", description="Action being performed")
    context: Optional[Dict[str, Any]] = Field(None, description="Additional context attributes")

class AccessEvaluationResponseSchema(BaseModel):
    decision: bool = Field(..., description="True if access is allowed")
    matched_policies: List[str] = Field(..., description="Policies that matched")
    details: Dict[str, Any] = Field(..., description="Evaluation details")
