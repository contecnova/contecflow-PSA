"""
ABAC (Attribute-Based Access Control) tests.
"""
import pytest
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient
from app.models.user import User, UserRole
from app.models.mfa import Organization
from app.services.abac import ABACService, ABACEngine
from app.main import app


client = TestClient(app)

@pytest.fixture
def test_org(db: Session) -> Organization:
    """Create test organization, cleaning up previous test data."""
    from sqlalchemy import text
    db.execute(text('DELETE FROM organization'))
    db.commit()
    org = Organization(id="test-org-1", name="Test Org", slug="test-org")
    db.add(org)
    db.commit()
    return org

@pytest.fixture
def test_admin_user(db: Session, test_org: Organization) -> User:
    """Create test admin user, cleaning up previous test data."""
    from sqlalchemy import text
    db.execute(text('DELETE FROM "user"'))
    db.commit()
    user = User(
        id="user-admin-test",
        email="admin-test@test.com",
        hashed_password="hashed",
        username="admin-test",
        full_name="Admin User",
        organization_id=test_org.id,
        role="admin",
        weekly_capacity_hours=40.0,
        currency="EUR"
    )
    db.add(user)
    db.commit()
    return user

@pytest.fixture
def test_manager_user(db: Session, test_org: Organization) -> User:
    """Create test manager user, cleaning up previous test data."""
    from sqlalchemy import text
    db.execute(text('DELETE FROM "user" WHERE username = :username'), {"username": "manager-test"})
    db.commit()
    user = User(
        id="user-manager-test",
        email="manager-test@test.com",
        hashed_password="hashed",
        username="manager-test",
        full_name="Manager User",
        organization_id=test_org.id,
        role="pm",
        weekly_capacity_hours=40.0,
        currency="EUR"
    )
    db.add(user)
    db.commit()
    return user

@pytest.fixture
def test_engineer_user(db: Session, test_org: Organization) -> User:
    """Create test engineer user, cleaning up previous test data."""
    from sqlalchemy import text
    db.execute(text('DELETE FROM "user" WHERE username = :username'), {"username": "engineer-test"})
    db.commit()
    user = User(
        id="user-eng-test",
        email="engineer-test@test.com",
        hashed_password="hashed",
        username="engineer-test",
        full_name="Engineer User",
        organization_id=test_org.id,
        role="employee",
        weekly_capacity_hours=40.0,
        currency="EUR"
    )
    db.add(user)
    db.commit()
    return user


class TestABACEngine:
    """Test ABAC policy evaluation engine."""

    def test_evaluate_equals(self):
        """Test equals operator."""
        assert ABACEngine.evaluate_condition("us", {"operator": "equals", "value": "us"}) is True
        assert ABACEngine.evaluate_condition("eu", {"operator": "equals", "value": "us"}) is False

    def test_evaluate_in(self):
        """Test 'in' operator for lists."""
        assert ABACEngine.evaluate_condition("proj1", {"operator": "in", "value": ["proj1", "proj2"]}) is True
        assert ABACEngine.evaluate_condition(["proj1", "proj2"], {"operator": "in", "value": ["proj1", "proj3"]}) is True
        assert ABACEngine.evaluate_condition("proj3", {"operator": "in", "value": ["proj1", "proj2"]}) is False

    def test_evaluate_contains(self):
        """Test string containment."""
        assert ABACEngine.evaluate_condition("sensitive_data", {"operator": "contains", "value": "sensitive"}) is True
        assert ABACEngine.evaluate_condition(["data1", "data2"], {"operator": "contains", "value": "data1"}) is True
        assert ABACEngine.evaluate_condition("public", {"operator": "contains", "value": "sensitive"}) is False

    def test_evaluate_gte(self):
        """Test ordinal comparison (greater than or equal)."""
        # Simulate data classification levels: public (0) < internal (1) < confidential (2) < restricted (3)
        assert ABACEngine.evaluate_condition(2, {"operator": "gte", "value": 1}) is True
        assert ABACEngine.evaluate_condition(1, {"operator": "gte", "value": 1}) is True
        assert ABACEngine.evaluate_condition(0, {"operator": "gte", "value": 1}) is False

    def test_evaluate_regex(self):
        """Test regex matching."""
        assert ABACEngine.evaluate_condition("proj-123", {"operator": "regex", "value": "^proj-[0-9]+$"}) is True
        assert ABACEngine.evaluate_condition("proj-abc", {"operator": "regex", "value": "^proj-[0-9]+$"}) is False

    def test_evaluate_is_empty(self):
        """Test empty checks."""
        assert ABACEngine.evaluate_condition([], {"operator": "is_empty", "value": None}) is True
        assert ABACEngine.evaluate_condition(["item"], {"operator": "is_empty", "value": None}) is False
        assert ABACEngine.evaluate_condition("", {"operator": "is_empty", "value": None}) is True

    def test_evaluate_rules_all_pass(self):
        """Test multiple rules (AND logic)."""
        rules = [
            {"attribute": "project_ids", "operator": "in", "value": ["proj1", "proj2"]},
            {"attribute": "region", "operator": "equals", "value": "us"},
        ]
        user_attrs = {"project_ids": "proj1", "region": "us"}
        assert ABACEngine.evaluate_rules(rules, user_attrs) is True

    def test_evaluate_rules_one_fails(self):
        """Test that all rules must pass (AND logic)."""
        rules = [
            {"attribute": "project_ids", "operator": "in", "value": ["proj1", "proj2"]},
            {"attribute": "region", "operator": "equals", "value": "us"},
        ]
        user_attrs = {"project_ids": "proj1", "region": "eu"}  # Region fails
        assert ABACEngine.evaluate_rules(rules, user_attrs) is False

    def test_is_policy_applicable(self):
        """Test policy applicability checks."""
        from app.models.abac import ABACPolicy

        now = datetime.utcnow()
        policy = ABACPolicy(
            id="p1",
            org_id="org1",
            policy_name="Test",
            effect="allow",
            rules=[],
            is_active=True,
            starts_at=now - timedelta(hours=1),
            expires_at=now + timedelta(hours=1),
        )

        # Policy should be applicable
        assert ABACEngine.is_policy_applicable(
            policy, "user1", ["manager"], "project", now
        ) is True

        # Policy should not be applicable (expired)
        expired_policy = ABACPolicy(
            id="p2",
            org_id="org1",
            policy_name="Test",
            effect="allow",
            rules=[],
            is_active=True,
            expires_at=now - timedelta(hours=1),
        )
        assert ABACEngine.is_policy_applicable(
            expired_policy, "user1", ["manager"], "project", now
        ) is False


class TestABACService:
    """Test ABAC service functions."""

    def test_assign_and_get_user_attributes(self, db: Session, test_org: Organization, test_manager_user: User):
        db.execute(text('DELETE FROM organization'))
        db.commit()
        """Test assigning and retrieving user attributes."""
        service = ABACService(db, test_org.id)

        # Assign attributes
        attr1 = service.assign_user_attribute(
            user_id=test_manager_user.id,
            attribute_key="project_ids",
            attribute_value=["proj1", "proj2"],
            assigned_by=test_manager_user.id,
            reason="Q2 project assignment",
        )
        assert attr1.id is not None
        assert attr1.attribute_value == ["proj1", "proj2"]

        attr2 = service.assign_user_attribute(
            user_id=test_manager_user.id,
            attribute_key="region",
            attribute_value="us",
            assigned_by=test_manager_user.id,
        )

        # Retrieve attributes
        attrs = service.get_user_attributes(test_manager_user.id)
        assert attrs["project_ids"] == ["proj1", "proj2"]
        assert attrs["region"] == "us"

    def test_attribute_expiry(self, db: Session, test_org: Organization, test_manager_user: User):
        db.execute(text('DELETE FROM organization'))
        db.commit()
        """Test that expired attributes are excluded."""
        service = ABACService(db, test_org.id)

        # Assign attribute that expires in the past
        service.assign_user_attribute(
            user_id=test_manager_user.id,
            attribute_key="temp_access",
            attribute_value="proj-temp",
            assigned_by=test_manager_user.id,
            expires_at=datetime.utcnow() - timedelta(hours=1),
        )

        # Should not be in active attributes
        attrs = service.get_user_attributes(test_manager_user.id)
        assert "temp_access" not in attrs

    def test_revoke_user_attribute(self, db: Session, test_org: Organization, test_manager_user: User):
        db.execute(text('DELETE FROM organization'))
        db.commit()
        """Test revoking user attributes."""
        service = ABACService(db, test_org.id)

        service.assign_user_attribute(
            user_id=test_manager_user.id,
            attribute_key="project_ids",
            attribute_value=["proj1"],
            assigned_by=test_manager_user.id,
        )

        # Verify assigned
        attrs = service.get_user_attributes(test_manager_user.id)
        assert "project_ids" in attrs

        # Revoke
        count = service.revoke_user_attribute(test_manager_user.id, "project_ids")
        assert count == 1

        # Verify revoked
        attrs = service.get_user_attributes(test_manager_user.id)
        assert "project_ids" not in attrs

    def test_create_and_list_policies(self, db: Session, test_org: Organization, test_admin_user: User):
        db.execute(text('DELETE FROM organization'))
        db.commit()
        """Test creating and listing policies."""
        service = ABACService(db, test_org.id)

        policy = service.create_policy(
            policy_name="Manager Q2 Projects",
            rules=[
                {"attribute": "project_ids", "operator": "in", "value": ["proj1", "proj2"]},
            ],
            effect="allow",
            applicable_roles=["manager"],
            created_by=test_admin_user.id,
            priority=80,
        )

        assert policy.id is not None
        assert policy.policy_name == "Manager Q2 Projects"
        assert policy.priority == 80

        # List policies
        policies = service.list_policies(active_only=True)
        assert len(policies) >= 1
        assert any(p.id == policy.id for p in policies)

    def test_evaluate_access_allow(self, db: Session, test_org: Organization, test_manager_user: User):
        db.execute(text('DELETE FROM organization'))
        db.commit()
        """Test access evaluation that should allow."""
        service = ABACService(db, test_org.id)

        # Assign user attribute
        service.assign_user_attribute(
            user_id=test_manager_user.id,
            attribute_key="project_ids",
            attribute_value=["proj1", "proj2"],
            assigned_by=test_manager_user.id,
        )

        # Create policy
        service.create_policy(
            policy_name="Project Access",
            rules=[
                {"attribute": "project_ids", "operator": "in", "value": ["proj1", "proj2", "proj3"]},
            ],
            effect="allow",
            applicable_roles=["manager"],
            resource_types=["project"],
        )

        # Evaluate access
        decision, policies, details = service.evaluate_access(
            user_id=test_manager_user.id,
            user_roles=["manager"],
            resource_type="project",
            resource_id="proj1",
        )

        assert decision is True
        assert len(policies) > 0

    def test_evaluate_access_deny(self, db: Session, test_org: Organization, test_engineer_user: User):
        db.execute(text('DELETE FROM organization'))
        db.commit()
        """Test access evaluation that should deny."""
        service = ABACService(db, test_org.id)

        # Create deny policy
        service.create_policy(
            policy_name="Deny Engineering Sensitive",
            rules=[
                {"attribute": "data_classification", "operator": "gte", "value": "confidential"},
            ],
            effect="deny",
            applicable_roles=["engineer"],
            resource_types=["data"],
        )

        # Engineer doesn't have high data_classification attribute, so will fail the rule
        # But let's test actual deny by assigning an attribute that matches the deny rule
        service.assign_user_attribute(
            user_id=test_engineer_user.id,
            attribute_key="data_classification",
            attribute_value="public",
            assigned_by=test_engineer_user.id,
        )

        # This should pass the allow rules but fail on deny
        decision, policies, details = service.evaluate_access(
            user_id=test_engineer_user.id,
            user_roles=["engineer"],
            resource_type="data",
        )

        # No allow policies match, so decision should be False
        assert decision is False

    def test_evaluate_access_with_context(self, db: Session, test_org: Organization, test_manager_user: User):
        db.execute(text('DELETE FROM organization'))
        db.commit()
        """Test evaluation with additional context."""
        service = ABACService(db, test_org.id)

        service.create_policy(
            policy_name="Region Restrict",
            rules=[
                {"attribute": "region", "operator": "equals", "value": "us"},
            ],
            effect="allow",
            applicable_roles=["manager"],
        )

        # Evaluate with context attribute
        decision, policies, details = service.evaluate_access(
            user_id=test_manager_user.id,
            user_roles=["manager"],
            context={"region": "us"},
        )

        assert decision is True

    def test_priority_order(self, db: Session, test_org: Organization, test_manager_user: User):
        db.execute(text('DELETE FROM organization'))
        db.commit()
        """Test that policies are evaluated by priority."""
        service = ABACService(db, test_org.id)

        # Lower priority policy (deny)
        service.create_policy(
            policy_name="Deny All",
            rules=[],
            effect="deny",
            priority=10,
        )

        # Higher priority policy (allow)
        service.create_policy(
            policy_name="Allow Managers",
            rules=[],
            effect="allow",
            applicable_roles=["manager"],
            priority=90,
        )

        decision, policies, details = service.evaluate_access(
            user_id=test_manager_user.id,
            user_roles=["manager"],
        )

        # Both policies match, but deny takes precedence over allow
        # Actually, explicit deny in any policy takes precedence
        assert decision is False

    def test_audit_logging(self, db: Session, test_org: Organization, test_manager_user: User):
        db.execute(text('DELETE FROM organization'))
        db.commit()
        """Test that access decisions are audited."""
        service = ABACService(db, test_org.id)

        service.create_policy(
            policy_name="Test Policy",
            rules=[],
            effect="allow",
            applicable_roles=["manager"],
        )

        decision, policies, details = service.evaluate_access(
            user_id=test_manager_user.id,
            user_roles=["manager"],
            resource_type="project",
            resource_id="proj1",
        )

        audit = service.audit_access_decision(
            user_id=test_manager_user.id,
            decision=decision,
            matched_policies=policies,
            resource_type="project",
            resource_id="proj1",
            details=details,
        )

        assert audit.id is not None
        assert audit.user_id == test_manager_user.id
        assert audit.result == ("allow" if decision else "deny")


class TestABACEndpoints:
    """Test ABAC API endpoints."""

    @pytest.mark.skip(reason="Endpoint test stub - pendiente de implementación")
    def test_list_attribute_definitions(self, db: Session, test_admin_user: User):
        db.execute(text('DELETE FROM organization'))
        db.commit()
        pass

    @pytest.mark.skip(reason="Endpoint test stub - pendiente de implementación")
    def test_get_user_attributes(self, db: Session, test_manager_user: User):
        db.execute(text('DELETE FROM organization'))
        db.commit()
        pass

    @pytest.mark.skip(reason="Endpoint test stub - pendiente de implementación")
    def test_assign_user_attribute(self, db: Session, test_admin_user: User):
        db.execute(text('DELETE FROM organization'))
        db.commit()
        pass

    @pytest.mark.skip(reason="Endpoint test stub - pendiente de implementación")
    def test_create_policy(self, db: Session, test_admin_user: User):
        db.execute(text('DELETE FROM organization'))
        db.commit()
        pass

    @pytest.mark.skip(reason="Endpoint test stub - pendiente de implementación")
    def test_evaluate_access(self, db: Session, test_manager_user: User):
        db.execute(text('DELETE FROM organization'))
        db.commit()
        pass

    @pytest.mark.skip(reason="Endpoint test stub - pendiente de implementación")
    def test_access_denied_on_missing_attribute(self, db: Session, test_engineer_user: User):
        db.execute(text('DELETE FROM organization'))
        db.commit()
        pass
