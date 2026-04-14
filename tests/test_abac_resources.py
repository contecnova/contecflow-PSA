"""
Tests for ABAC enforcement in resource endpoints (timesheets, expenses, documents)
and ABAC admin dashboard analytics API.
"""
import pytest
from fastapi.testclient import TestClient

from tests.conftest import auth


@pytest.fixture()
def admin_with_org(admin_token, db, client):
    """Ensures admin test user has an organization_id for org-scoped endpoints."""
    from app.models.mfa import Organization
    from app.models.user import User
    org = Organization(id="abac-test-org", name="ABAC Test Org", slug="abac-test-org")
    db.add(org)
    db.flush()
    admin = db.query(User).filter(User.id == "admin-test-id").first()
    admin.organization_id = "abac-test-org"
    db.commit()
    return admin_token


# ── ABAC admin dashboard ──────────────────────────────────────────────────

class TestABACAdminDashboard:
    def test_overview_admin(self, client, admin_with_org):
        res = client.get("/api/v1/abac/admin/overview", headers=auth(admin_with_org))
        assert res.status_code == 200
        data = res.json()
        assert "total_policies" in data
        assert "deny_rate" in data

    def test_overview_non_admin_forbidden(self, client, dev_token):
        res = client.get("/api/v1/abac/admin/overview", headers=auth(dev_token))
        assert res.status_code == 403

    def test_attributes_summary(self, client, admin_with_org):
        res = client.get("/api/v1/abac/admin/attributes/summary", headers=auth(admin_with_org))
        assert res.status_code == 200
        assert isinstance(res.json(), list)

    def test_policies_effectiveness(self, client, admin_with_org):
        res = client.get("/api/v1/abac/admin/policies/effectiveness", headers=auth(admin_with_org))
        assert res.status_code == 200
        assert isinstance(res.json(), list)

    def test_access_patterns(self, client, admin_with_org):
        res = client.get("/api/v1/abac/admin/access-patterns", headers=auth(admin_with_org))
        assert res.status_code == 200
        data = res.json()
        assert "top_denied_users" in data
        assert "daily_trend" in data

    def test_user_access_profile(self, client, admin_with_org):
        res = client.get("/api/v1/abac/admin/users/dev-test-id/access-profile", headers=auth(admin_with_org))
        assert res.status_code == 200
        data = res.json()
        assert "attributes" in data
        assert "applicable_policies" in data

    def test_audit_log_admin(self, client, admin_with_org):
        res = client.get("/api/v1/abac/admin/audit-log", headers=auth(admin_with_org))
        assert res.status_code == 200
        data = res.json()
        assert "items" in data
        assert "total" in data

    def test_audit_log_stats(self, client, admin_with_org):
        res = client.get("/api/v1/abac/admin/audit-log/stats", headers=auth(admin_with_org))
        assert res.status_code == 200
        data = res.json()
        assert "total" in data

    def test_overview_no_org_returns_400(self, client, admin_token):
        """Admin without org_id returns 400 from org-scoped endpoint."""
        res = client.get("/api/v1/abac/admin/overview", headers=auth(admin_token))
        assert res.status_code == 400


# ── ABAC enforcement: timesheets ──────────────────────────────────────────────

class TestABACTimesheetEnforcement:
    """Without any ABAC deny policy, all manager requests should pass through."""

    def test_team_timesheets_manager_allowed(self, client, admin_token):
        res = client.get("/api/v1/timesheets/team", headers=auth(admin_token))
        # No ABAC policy → fail-open, 200 OK
        assert res.status_code == 200

    def test_team_timesheets_pm_allowed(self, client, pm_token):
        res = client.get("/api/v1/timesheets/team", headers=auth(pm_token))
        assert res.status_code == 200

    def test_team_timesheets_employee_forbidden(self, client, dev_token):
        """Employees are filtered by require_any_manager dep, not ABAC."""
        res = client.get("/api/v1/timesheets/team", headers=auth(dev_token))
        assert res.status_code == 403


# ── ABAC enforcement: expenses ─────────────────────────────────────────────────

class TestABACExpenseEnforcement:
    def test_pending_expenses_manager_allowed(self, client, admin_token):
        res = client.get("/api/v1/expenses/pending", headers=auth(admin_token))
        assert res.status_code == 200

    def test_pending_expenses_employee_forbidden(self, client, dev_token):
        res = client.get("/api/v1/expenses/pending", headers=auth(dev_token))
        assert res.status_code == 403

    def test_team_expenses_pm_allowed(self, client, pm_token):
        res = client.get("/api/v1/expenses/team", headers=auth(pm_token))
        assert res.status_code == 200

    def test_create_expense_employee_allowed(self, client, dev_token):
        """Any authenticated user can create their own expense — ABAC fail-open."""
        payload = {
            "category": "travel",
            "amount": 50.0,
            "currency": "EUR",
            "expense_date": "2025-01-15",
            "description": "Taxi to client",
        }
        res = client.post("/api/v1/expenses", json=payload, headers=auth(dev_token))
        assert res.status_code in (200, 201)


# ── ABAC enforcement: documents ────────────────────────────────────────────────

class TestABACDocumentEnforcement:
    def test_create_document_allowed_fail_open(self, client, dev_token):
        """Without deny policy, document creation goes through."""
        payload = {
            "title": "Test Doc",
            "category": "other",
        }
        res = client.post("/api/v1/documents", json=payload, headers=auth(dev_token))
        assert res.status_code in (200, 201)

    def test_get_nonexistent_document_404(self, client, admin_token):
        """ABAC check happens before 404 lookup; fail-open then document lookup → 404."""
        res = client.get("/api/v1/documents/nonexistent-doc-id", headers=auth(admin_token))
        assert res.status_code == 404

    def test_upload_document_allowed_fail_open(self, client, dev_token):
        """Multipart upload passes ABAC check on create action."""
        import io
        content = b"%PDF-1.4 test document"
        res = client.post(
            "/api/v1/documents/upload",
            files={"file": ("test.pdf", io.BytesIO(content), "application/pdf")},
            data={"title": "Test Upload", "category": "other"},
            headers=auth(dev_token),
        )
        # Should pass ABAC (fail-open) and not return 403
        assert res.status_code != 403


# ── enforce_abac helper unit tests ──────────────────────────────────────────────

class TestEnforceABACHelper:
    def test_superadmin_bypasses_abac(self, db):
        from app.core.abac_enforce import enforce_abac
        from app.models.user import User, UserRole, UserStatus

        su = db.query(User).filter(User.id == "admin-test-id").first()
        su.is_superadmin = True
        db.commit()

        # Should NOT raise — superadmin bypass
        enforce_abac(db, su, "timesheet", action="read")

        su.is_superadmin = False
        db.commit()

    def test_no_org_user_bypasses_abac(self, db):
        from app.core.abac_enforce import enforce_abac
        from app.models.user import User, UserRole, UserStatus
        import uuid

        noorg = User(
            id=f"noorg-{uuid.uuid4().hex[:8]}",
            username=f"noorg_{uuid.uuid4().hex[:8]}",
            email=f"noorg_{uuid.uuid4().hex[:8]}@test.com",
            full_name="No Org",
            role=UserRole.pm,
            status=UserStatus.active,
            is_active=True,
            hashed_password="x",
        )
        db.add(noorg)
        db.commit()

        # No organization_id → fail-open, no exception
        enforce_abac(db, noorg, "expense", action="read")

    def test_user_with_org_no_deny_policy_allowed(self, db):
        from app.core.abac_enforce import enforce_abac
        from app.models.mfa import Organization
        from app.models.user import User, UserRole, UserStatus
        import uuid

        org = Organization(
            id=f"org-{uuid.uuid4().hex[:8]}",
            name="Test Org ABAC",
            slug=f"test-org-{uuid.uuid4().hex[:8]}",
        )
        db.add(org)
        db.flush()

        user = User(
            id=f"user-{uuid.uuid4().hex[:8]}",
            username=f"user_{uuid.uuid4().hex[:8]}",
            email=f"user_{uuid.uuid4().hex[:8]}@test.com",
            full_name="Org User",
            role=UserRole.employee,
            status=UserStatus.active,
            is_active=True,
            organization_id=org.id,
            hashed_password="x",
        )
        db.add(user)
        db.commit()

        # No ABAC deny policies in DB → evaluates to allow
        enforce_abac(db, user, "document", action="read")

    def test_overview_non_admin_forbidden(self, client, dev_token):
        res = client.get("/api/v1/abac/admin/overview", headers=auth(dev_token))
        assert res.status_code == 403

    def test_attributes_summary(self, client, admin_token):
        res = client.get("/api/v1/abac/admin/attributes/summary", headers=auth(admin_token))
        assert res.status_code == 200
        assert isinstance(res.json(), list)

    def test_policies_effectiveness(self, client, admin_token):
        res = client.get("/api/v1/abac/admin/policies/effectiveness", headers=auth(admin_token))
        assert res.status_code == 200
        assert isinstance(res.json(), list)

    def test_access_patterns(self, client, admin_token):
        res = client.get("/api/v1/abac/admin/access-patterns", headers=auth(admin_token))
        assert res.status_code == 200
        data = res.json()
        assert "top_denied_users" in data
        assert "daily_trend" in data

    def test_user_access_profile(self, client, admin_token):
        res = client.get("/api/v1/abac/admin/users/dev-test-id/access-profile", headers=auth(admin_token))
        assert res.status_code == 200
        data = res.json()
        assert "attributes" in data
        assert "applicable_policies" in data

    def test_audit_log_admin(self, client, admin_token):
        res = client.get("/api/v1/abac/admin/audit-log", headers=auth(admin_token))
        assert res.status_code == 200
        data = res.json()
        assert "items" in data
        assert "total" in data

    def test_audit_log_stats(self, client, admin_token):
        res = client.get("/api/v1/abac/admin/audit-log/stats", headers=auth(admin_token))
        assert res.status_code == 200
        data = res.json()
        assert "total" in data


# ── ABAC enforcement: timesheets ─────────────────────────────────────────────

class TestABACTimesheetEnforcement:
    """Without any ABAC deny policy, all manager requests should pass through."""

    def test_team_timesheets_manager_allowed(self, client, admin_token):
        res = client.get("/api/v1/timesheets/team", headers=auth(admin_token))
        # No ABAC policy → fail-open, 200 OK
        assert res.status_code == 200

    def test_team_timesheets_pm_allowed(self, client, pm_token):
        res = client.get("/api/v1/timesheets/team", headers=auth(pm_token))
        assert res.status_code == 200

    def test_team_timesheets_employee_forbidden(self, client, dev_token):
        """Employees are filtered by require_any_manager dep, not ABAC."""
        res = client.get("/api/v1/timesheets/team", headers=auth(dev_token))
        assert res.status_code == 403


# ── ABAC enforcement: expenses ───────────────────────────────────────────────

class TestABACExpenseEnforcement:
    def test_pending_expenses_manager_allowed(self, client, admin_token):
        res = client.get("/api/v1/expenses/pending", headers=auth(admin_token))
        assert res.status_code == 200

    def test_pending_expenses_employee_forbidden(self, client, dev_token):
        res = client.get("/api/v1/expenses/pending", headers=auth(dev_token))
        assert res.status_code == 403

    def test_team_expenses_pm_allowed(self, client, pm_token):
        res = client.get("/api/v1/expenses/team", headers=auth(pm_token))
        assert res.status_code == 200

    def test_create_expense_employee_allowed(self, client, dev_token):
        """Any authenticated user can create their own expense — ABAC fail-open."""
        payload = {
            "category": "travel",
            "amount": 50.0,
            "currency": "EUR",
            "expense_date": "2025-01-15",
            "description": "Taxi to client",
        }
        res = client.post("/api/v1/expenses", json=payload, headers=auth(dev_token))
        # fail-open: no org_id on user → ABAC bypass → 200/201
        assert res.status_code in (200, 201)


# ── ABAC enforcement: documents ──────────────────────────────────────────────

class TestABACDocumentEnforcement:
    def test_create_document_allowed_fail_open(self, client, dev_token):
        """Without deny policy, document creation goes through."""
        payload = {
            "title": "Test Doc",
            "category": "other",
        }
        res = client.post("/api/v1/documents", json=payload, headers=auth(dev_token))
        # ABAC fail-open (no org_id) → 201 or passes ABAC
        assert res.status_code in (200, 201)

    def test_get_nonexistent_document_404(self, client, admin_token):
        """ABAC check happens before 404, but with fail-open and non-existent doc → 404."""
        res = client.get("/api/v1/documents/nonexistent-doc-id", headers=auth(admin_token))
        # ABAC fail-open then document lookup → 404
        assert res.status_code == 404

    def test_upload_document_allowed_fail_open(self, client, dev_token):
        """Multipart upload passes ABAC check on create action."""
        import io
        content = b"%PDF-1.4 test document"
        res = client.post(
            "/api/v1/documents/upload",
            files={"file": ("test.pdf", io.BytesIO(content), "application/pdf")},
            data={"title": "Test Upload", "category": "other"},
            headers=auth(dev_token),
        )
        # Should pass ABAC (fail-open) and proceed to file upload logic
        # May fail on storage but not on ABAC (not 403)
        assert res.status_code != 403


# ── enforce_abac helper unit tests ──────────────────────────────────────────

class TestEnforceABACHelper:
    def test_superadmin_bypasses_abac(self, db):
        from app.core.abac_enforce import enforce_abac
        from app.models.user import User, UserRole, UserStatus

        su = User(
            id="su-test",
            username="superadmin_t",
            email="su@test.com",
            full_name="Super Admin",
            role=UserRole.admin,
            status=UserStatus.active,
            is_active=True,
            is_superadmin=True,
            hashed_password="x",
        )
        db.add(su)
        db.commit()

        # Should NOT raise — superadmin bypass
        enforce_abac(db, su, "timesheet", action="read")

    def test_no_org_user_bypasses_abac(self, db):
        from app.core.abac_enforce import enforce_abac
        from app.models.user import User, UserRole, UserStatus

        noorg = User(
            id="noorg-test",
            username="noorg_user",
            email="noorg@test.com",
            full_name="No Org",
            role=UserRole.pm,
            status=UserStatus.active,
            is_active=True,
            organization_id=None,
            hashed_password="x",
        )
        db.add(noorg)
        db.commit()

        # No org_id → fail-open, no exception
        enforce_abac(db, noorg, "expense", action="read")

    def test_user_with_org_no_deny_policy_allowed(self, db):
        from app.core.abac_enforce import enforce_abac
        from app.models.mfa import Organization
        from app.models.user import User, UserRole, UserStatus
        import uuid

        org = Organization(
            id="org-abac-test",
            name="Test Org ABAC",
            slug="test-org-abac",
        )
        db.add(org)
        db.flush()

        user = User(
            id=f"user-{uuid.uuid4().hex[:8]}",
            username=f"user_{uuid.uuid4().hex[:8]}",
            email=f"user_{uuid.uuid4().hex[:8]}@test.com",
            full_name="Org User",
            role=UserRole.employee,
            status=UserStatus.active,
            is_active=True,
            organization_id="org-abac-test",
            hashed_password="x",
        )
        db.add(user)
        db.commit()

        # No ABAC deny policies in DB → evaluates to allow
        enforce_abac(db, user, "document", action="read")
