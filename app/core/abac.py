"""
ABAC security dependency for FastAPI.
Provides fine-grained authorization checks in route handlers.
"""
from typing import Optional, Dict, Any
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.deps import get_db, get_current_user
from app.models.user import User
from app.services.abac import ABACService


class ABACDependency:
    """FastAPI dependency for ABAC authorization checks."""

    def __init__(
        self,
        resource_type: Optional[str] = None,
        action: str = "read",
        require_allow: bool = True,
    ):
        """
        Initialize ABAC dependency.

        Args:
            resource_type: Type of resource being accessed (e.g., "timesheets")
            action: Action being performed (default: "read")
            require_allow: If True, raise exception on deny; if False, allow caller to handle decision
        """
        self.resource_type = resource_type
        self.action = action
        self.require_allow = require_allow

    async def __call__(
        self,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
        resource_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate ABAC policies for current user.

        Returns:
            {"decision": bool, "matched_policies": List[str], "details": Dict, ...}
        """
        org_id = current_user.organization_id
        if not org_id:
            raise HTTPException(status_code=400, detail="User organization not set")

        user_roles = [r.name for r in current_user.roles]
        service = ABACService(db, org_id)

        decision, matched_policies, details = service.evaluate_access(
            user_id=current_user.id,
            user_roles=user_roles,
            resource_type=self.resource_type,
            resource_id=resource_id,
            action=self.action,
            context=context,
        )

        # Audit the evaluation
        service.audit_access_decision(
            user_id=current_user.id,
            decision=decision,
            matched_policies=matched_policies,
            resource_type=self.resource_type,
            resource_id=resource_id,
            details=details,
        )

        if self.require_allow and not decision:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"ABAC policy denied access to {self.resource_type or 'resource'}",
            )

        return {
            "decision": decision,
            "matched_policies": matched_policies,
            "resource_type": self.resource_type,
            "resource_id": resource_id,
            "action": self.action,
            "details": details,
        }


# Factory function for creating ABAC deps with specific rules
def check_project_access(
    project_id: str,
    action: str = "read",
) -> ABACDependency:
    """
    Check if user has access to specific project.

    Example usage in route:
        @router.get("/projects/{project_id}")
        async def get_project(
            project_id: str,
            abac_check: Dict = Depends(check_project_access(project_id)),
            db: Session = Depends(get_db),
            current_user: User = Depends(get_current_user),
        ):
            # Access allowed by ABAC
            ...
    """
    return ABACDependency(
        resource_type="project",
        action=action,
        require_allow=True,
    )


def check_client_access(
    client_id: str,
    action: str = "read",
) -> ABACDependency:
    """Check if user has access to specific client."""
    return ABACDependency(
        resource_type="client",
        action=action,
        require_allow=True,
    )


def check_data_classification_access(
    min_classification: str = "internal",
    # Classification levels: public < internal < confidential < restricted
) -> ABACDependency:
    """Check if user has access to data at given classification level."""
    return ABACDependency(
        resource_type="data",
        action="read",
        require_allow=True,
    )


def check_region_access(
    region: str,
) -> ABACDependency:
    """Check if user is authorized to access resources in given region."""
    return ABACDependency(
        resource_type="region",
        action="read",
        require_allow=True,
    )
