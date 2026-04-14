"""
ABAC (Attribute-Based Access Control) service for fine-grained authorization.

Provides policy evaluation engine, attribute management, and access control decisions
that work in conjunction with RBAC (role-based access control).
"""
import re
import json
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from sqlalchemy.orm import Session
from app.models.abac import ABACPolicy, UserAttribute, AttributeDefinition, PolicyAudit
from app.models.user import User
from app.core.security import get_password_hash
import uuid


class ABACEngine:
    """Policy evaluation engine for attribute-based access control."""

    @staticmethod
    def evaluate_condition(user_attribute_value: Any, rule: Dict[str, Any]) -> bool:
        """
        Evaluate a single attribute condition.

        Args:
            user_attribute_value: Value from user's attributes
            rule: {"attribute": key, "operator": op, "value": val}

        Returns:
            True if condition is met, False otherwise
        """
        operator = rule.get("operator", "equals")
        expected_value = rule.get("value")

        # Handle None values
        if user_attribute_value is None:
            return operator in ["not_equals"] if expected_value is not None else False

        try:
            if operator == "equals":
                return user_attribute_value == expected_value

            elif operator == "not_equals":
                return user_attribute_value != expected_value

            elif operator == "in":
                # user_attribute_value can be single or list
                if isinstance(user_attribute_value, list):
                    return any(v in expected_value for v in user_attribute_value)
                else:
                    return user_attribute_value in expected_value

            elif operator == "not_in":
                if isinstance(user_attribute_value, list):
                    return all(v not in expected_value for v in user_attribute_value)
                else:
                    return user_attribute_value not in expected_value

            elif operator == "contains":
                # For string containment or list membership
                if isinstance(user_attribute_value, str):
                    return expected_value.lower() in user_attribute_value.lower()
                elif isinstance(user_attribute_value, list):
                    return expected_value in user_attribute_value
                return False

            elif operator == "not_contains":
                if isinstance(user_attribute_value, str):
                    return expected_value.lower() not in user_attribute_value.lower()
                elif isinstance(user_attribute_value, list):
                    return expected_value not in user_attribute_value
                return False

            elif operator == "starts_with":
                return str(user_attribute_value).startswith(str(expected_value))

            elif operator == "ends_with":
                return str(user_attribute_value).endswith(str(expected_value))

            elif operator == "regex":
                return bool(re.match(expected_value, str(user_attribute_value)))

            elif operator == "gte":  # Greater than or equal (for ordinal values)
                return user_attribute_value >= expected_value

            elif operator == "lte":  # Less than or equal
                return user_attribute_value <= expected_value

            elif operator == "gt":  # Greater than
                return user_attribute_value > expected_value

            elif operator == "lt":  # Less than
                return user_attribute_value < expected_value

            elif operator == "is_empty":
                if isinstance(user_attribute_value, list):
                    return len(user_attribute_value) == 0
                return user_attribute_value == "" or user_attribute_value is None

            elif operator == "is_not_empty":
                if isinstance(user_attribute_value, list):
                    return len(user_attribute_value) > 0
                return user_attribute_value != "" and user_attribute_value is not None

            else:
                return False

        except (TypeError, AttributeError):
            return False

    @staticmethod
    def evaluate_rules(rules: List[Dict[str, Any]], user_attributes: Dict[str, Any]) -> bool:
        """
        Evaluate all rules in a policy (AND logic: all must pass).

        Args:
            rules: List of rule conditions
            user_attributes: Map of attribute_key -> value for the user

        Returns:
            True if all rules match, False otherwise
        """
        for rule in rules:
            attribute_key = rule.get("attribute")
            user_value = user_attributes.get(attribute_key)

            if not ABACEngine.evaluate_condition(user_value, rule):
                return False

        return True

    @staticmethod
    def is_policy_applicable(
        policy: ABACPolicy,
        user_id: str,
        user_roles: List[str],
        resource_type: Optional[str] = None,
        current_time: Optional[datetime] = None,
    ) -> bool:
        """
        Check if policy is applicable to this user/request without evaluating rules.

        Args:
            policy: The policy to check
            user_id: User ID
            user_roles: Roles assigned to user
            resource_type: Resource being accessed
            current_time: Current time (default: now)

        Returns:
            True if policy applies, False otherwise
        """
        if not policy.is_active:
            return False

        now = current_time or datetime.utcnow()

        # Check temporal constraints
        if policy.starts_at and now < policy.starts_at:
            return False
        if policy.expires_at and now > policy.expires_at:
            return False

        # Check subject users (if specified, user must be in list)
        if policy.subject_users and user_id not in policy.subject_users:
            return False

        # Check applicable roles (if specified, user must have at least one role)
        if policy.applicable_roles:
            if not any(role in policy.applicable_roles for role in user_roles):
                return False

        # Check resource types (if specified, resource must match)
        if policy.resource_types and resource_type:
            if resource_type not in policy.resource_types:
                return False

        return True


class ABACService:
    """ABAC service for managing policies, attributes, and access control decisions."""

    def __init__(self, db: Session, org_id: str):
        self.db = db
        self.org_id = org_id
        self.engine = ABACEngine()

    def assign_user_attribute(
        self,
        user_id: str,
        attribute_key: str,
        attribute_value: Any,
        assigned_by: str,
        reason: Optional[str] = None,
        expires_at: Optional[datetime] = None,
    ) -> UserAttribute:
        """Assign an attribute to a user."""
        attr = UserAttribute(
            id=str(uuid.uuid4()),
            user_id=user_id,
            org_id=self.org_id,
            attribute_key=attribute_key,
            attribute_value=attribute_value if isinstance(attribute_value, (list, dict)) else attribute_value,
            reason=reason,
            expires_at=expires_at,
            assigned_by=assigned_by,
        )
        self.db.add(attr)
        self.db.commit()
        return attr

    def revoke_user_attribute(self, user_id: str, attribute_key: str) -> int:
        """Remove all instances of an attribute for a user."""
        deleted = self.db.query(UserAttribute).filter(
            UserAttribute.user_id == user_id,
            UserAttribute.org_id == self.org_id,
            UserAttribute.attribute_key == attribute_key,
        ).delete()
        self.db.commit()
        return deleted

    def get_user_attributes(self, user_id: str) -> Dict[str, Any]:
        """
        Get all non-expired attributes for a user.

        Returns: {attribute_key: attribute_value, ...}
        """
        now = datetime.utcnow()
        attrs = self.db.query(UserAttribute).filter(
            UserAttribute.user_id == user_id,
            UserAttribute.org_id == self.org_id,
        ).all()

        result = {}
        for attr in attrs:
            # Skip expired attributes
            if attr.expires_at and attr.expires_at < now:
                continue

            # Aggregate multiple values for same attribute
            key = attr.attribute_key
            if key in result:
                # Convert to list if not already
                if not isinstance(result[key], list):
                    result[key] = [result[key]]
                if isinstance(attr.attribute_value, list):
                    result[key].extend(attr.attribute_value)
                else:
                    result[key].append(attr.attribute_value)
            else:
                result[key] = attr.attribute_value

        return result

    def create_policy(
        self,
        policy_name: str,
        rules: List[Dict[str, Any]],
        effect: str = "allow",
        created_by: str = None,
        resource_types: Optional[List[str]] = None,
        applicable_roles: Optional[List[str]] = None,
        subject_users: Optional[List[str]] = None,
        priority: int = 50,
        expires_at: Optional[datetime] = None,
        description: Optional[str] = None,
    ) -> ABACPolicy:
        """Create a new ABAC policy."""
        policy = ABACPolicy(
            id=str(uuid.uuid4()),
            org_id=self.org_id,
            policy_name=policy_name,
            description=description,
            effect=effect,
            rules=rules,
            resource_types=resource_types or [],
            applicable_roles=applicable_roles or [],
            subject_users=subject_users or [],
            priority=priority,
            expires_at=expires_at,
            created_by=created_by,
        )
        self.db.add(policy)
        self.db.commit()
        return policy

    def update_policy(self, policy_id: str, **kwargs) -> ABACPolicy:
        """Update an existing policy."""
        policy = self.db.query(ABACPolicy).filter(
            ABACPolicy.id == policy_id,
            ABACPolicy.org_id == self.org_id,
        ).one_or_404()

        for key, value in kwargs.items():
            if hasattr(policy, key):
                setattr(policy, key, value)

        policy.updated_at = datetime.utcnow()
        self.db.commit()
        return policy

    def delete_policy(self, policy_id: str) -> bool:
        """Soft delete a policy."""
        policy = self.db.query(ABACPolicy).filter(
            ABACPolicy.id == policy_id,
            ABACPolicy.org_id == self.org_id,
        ).one_or_404()
        policy.is_active = False
        self.db.commit()
        return True

    def list_policies(self, active_only: bool = True) -> List[ABACPolicy]:
        """List policies for org."""
        query = self.db.query(ABACPolicy).filter(ABACPolicy.org_id == self.org_id)
        if active_only:
            query = query.filter(ABACPolicy.is_active == True)
        return query.order_by(ABACPolicy.priority.desc()).all()

    def evaluate_access(
        self,
        user_id: str,
        user_roles: List[str],
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        action: str = "read",
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, List[str], Dict[str, Any]]:
        """
        Evaluate if user should be granted access to a resource.

        Returns:
            (decision: bool, matched_policies: List[str], evaluation_details: Dict)
        """
        context = context or {}
        matched_allow_policies = []
        matched_deny_policies = []

        # Get user's attributes
        user_attributes = self.get_user_attributes(user_id)

        # Merge context attributes
        evaluation_attrs = {**user_attributes, **context}

        # Get active policies sorted by priority
        policies = self.list_policies(active_only=True)
        policies.sort(key=lambda p: p.priority, reverse=True)

        # Evaluate policies in priority order
        for policy in policies:
            # Check if policy is applicable
            if not self.engine.is_policy_applicable(policy, user_id, user_roles, resource_type):
                continue

            # Evaluate policy rules
            if self.engine.evaluate_rules(policy.rules, evaluation_attrs):
                if policy.effect == "allow":
                    matched_allow_policies.append(policy.id)
                else:  # deny
                    matched_deny_policies.append(policy.id)

        # Decision logic: explicit deny takes precedence
        has_explicit_deny = len(matched_deny_policies) > 0
        decision = not has_explicit_deny and len(matched_allow_policies) > 0

        details = {
            "user_id": user_id,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "action": action,
            "matched_allow": matched_allow_policies,
            "matched_deny": matched_deny_policies,
            "user_attributes": user_attributes,
        }

        return decision, matched_allow_policies + matched_deny_policies, details

    def audit_access_decision(
        self,
        user_id: str,
        decision: bool,
        matched_policies: List[str],
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> PolicyAudit:
        """Create audit log entry for access decision."""
        audit = PolicyAudit(
            id=str(uuid.uuid4()),
            org_id=self.org_id,
            user_id=user_id,
            action="access_allowed" if decision else "access_denied",
            result="allow" if decision else "deny",
            resource_type=resource_type,
            resource_id=resource_id,
            matched_policies=matched_policies,
            evaluation_context=details,
        )
        self.db.add(audit)

        # Emit a SecurityEvent for denials so the SOC dashboard tracks them
        if not decision:
            try:
                from app.services.security_observability import SecurityEventService
                deny_policies = (details or {}).get("matched_deny", matched_policies)
                SecurityEventService(db=self.db, org_id=self.org_id).abac_denied(
                    user_id=user_id,
                    resource_type=resource_type or "unknown",
                    resource_id=resource_id or "",
                    matched_policies=deny_policies or [],
                )
            except Exception:  # noqa: BLE001
                pass

        self.db.commit()
        return audit

    def create_attribute_definition(
        self,
        attribute_key: str,
        attribute_type: str,  # "string", "list", "enum", "integer", "date"
        operators: List[str],
        created_by: str,
        description: Optional[str] = None,
        possible_values: Optional[List[Any]] = None,
    ) -> AttributeDefinition:
        """Define a new attribute type for policies."""
        attr_def = AttributeDefinition(
            id=str(uuid.uuid4()),
            org_id=self.org_id,
            attribute_key=attribute_key,
            attribute_type=attribute_type,
            description=description,
            possible_values=possible_values,
            operators=operators,
            created_by=created_by,
        )
        self.db.add(attr_def)
        self.db.commit()
        return attr_def

    def list_attribute_definitions(self, active_only: bool = True) -> List[AttributeDefinition]:
        """List available attributes for org."""
        query = self.db.query(AttributeDefinition).filter(
            AttributeDefinition.org_id == self.org_id
        )
        if active_only:
            query = query.filter(AttributeDefinition.is_active == True)
        return query.all()


# Pre-defined ABAC attribute definitions for common PSA use cases
DEFAULT_ABAC_ATTRIBUTES = [
    {
        "attribute_key": "project_ids",
        "attribute_type": "list",
        "description": "Projects the user can access",
        "operators": ["in", "not_in", "contains", "is_empty"],
    },
    {
        "attribute_key": "client_ids",
        "attribute_type": "list",
        "description": "Clients the user can access",
        "operators": ["in", "not_in", "contains", "is_empty"],
    },
    {
        "attribute_key": "region",
        "attribute_type": "enum",
        "description": "Geographic region(s) for data access",
        "possible_values": ["EMEA", "APAC", "Americas", "Canada", "EU", "US"],
        "operators": ["equals", "in", "not_equals"],
    },
    {
        "attribute_key": "data_classification",
        "attribute_type": "enum",
        "description": "Maximum data sensitivity level can access (higher value = more sensitive)",
        "possible_values": ["public", "internal", "confidential", "restricted"],
        "operators": ["gte", "lte", "equals"],
    },
    {
        "attribute_key": "team_ids",
        "attribute_type": "list",
        "description": "Teams the user belongs to",
        "operators": ["in", "contains", "is_empty"],
    },
    {
        "attribute_key": "department",
        "attribute_type": "enum",
        "description": "Department assignment",
        "possible_values": ["Engineering", "Sales", "HR", "Finance", "Operations", "Support"],
        "operators": ["equals", "in"],
    },
    {
        "attribute_key": "resource_types",
        "attribute_type": "list",
        "description": "Resource types the user can access (timesheets, expenses, documents, etc)",
        "operators": ["in", "contains"],
    },
    {
        "attribute_key": "cost_center",
        "attribute_type": "string",
        "description": "Cost center for budgeting and expense attribution",
        "operators": ["equals", "contains"],
    },
]
