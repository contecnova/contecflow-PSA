"""
test_grc.py — Tests for GRC (Governance, Risk & Compliance) module.

Covers:
  - Permission matrix seed and read
  - Permission matrix update
  - SoD rule CRUD
  - SoD violation logging (self-approval detection)
  - GRC audit log query
  - SoD check endpoint
"""
import pytest
from tests.conftest import auth


# ── Helpers ────────────────────────────────────────────────────────────────────

def _seed_matrix(client, token):
    res = client.post("/api/v1/grc/permissions/seed", headers=auth(token))
    assert res.status_code in (200, 201, 204), res.text
    return res


# ── Permission Matrix ─────────────────────────────────────────────────────────

class TestGRCPermissions:
    def test_seed_permissions_returns_ok(self, client, admin_token, db):
        res = _seed_matrix(client, admin_token)
        assert res.status_code in (200, 201, 204)

    def test_list_permissions_after_seed(self, client, admin_token, db):
        _seed_matrix(client, admin_token)
        res = client.get("/api/v1/grc/permissions", headers=auth(admin_token))
        assert res.status_code == 200
        data = res.json()
        # The matrix is returned as a dict or list; just check it is non-empty
        assert data

    def test_update_permission_flag(self, client, admin_token, db):
        _seed_matrix(client, admin_token)
        # Try to toggle a known role/module/action combination
        res = client.get("/api/v1/grc/permissions", headers=auth(admin_token))
        permissions = res.json()

        # The endpoint might return a nested dict or a list
        role = module = action = None
        if isinstance(permissions, dict):
            for r, mods in permissions.items():
                for m, acts in mods.items():
                    for a in acts:
                        role, module, action = r, m, a
                        break
                    if role:
                        break
                if role:
                    break
        elif isinstance(permissions, list) and permissions:
            p = permissions[0]
            role = p.get("role")
            module = p.get("module")
            action = p.get("action")

        if not (role and module and action):
            pytest.skip("No permissions to toggle — seed may have different structure")

        res = client.patch(
            f"/api/v1/grc/permissions/{role}/{module}/{action}",
            json={"allowed": False},
            headers=auth(admin_token),
        )
        assert res.status_code in (200, 204), res.text

    def test_non_admin_cannot_access_permissions(self, client, dev_token, db):
        res = client.get("/api/v1/grc/permissions", headers=auth(dev_token))
        assert res.status_code in (403, 401)


# ── SoD Rules ─────────────────────────────────────────────────────────────────

class TestSodRules:
    def _create_rule(self, client, token, name="test-sod-rule"):
        return client.post(
            "/api/v1/grc/sod-rules",
            json={
                "name": name,
                "description": "Test SoD rule",
                "module_a": "invoices",
                "action_a": "crear",
                "module_b": "invoices",
                "action_b": "aprobar",
                "enforcement": "block",
            },
            headers=auth(token),
        )

    def test_create_sod_rule(self, client, admin_token, db):
        res = self._create_rule(client, admin_token)
        assert res.status_code in (200, 201), res.text
        data = res.json()
        assert data.get("module_a") == "invoices"

    def test_list_sod_rules(self, client, admin_token, db):
        self._create_rule(client, admin_token)
        res = client.get("/api/v1/grc/sod-rules", headers=auth(admin_token))
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_update_sod_rule(self, client, admin_token, db):
        rule = self._create_rule(client, admin_token).json()
        rule_id = rule.get("id")
        res = client.patch(
            f"/api/v1/grc/sod-rules/{rule_id}",
            json={"enforcement": "warn"},
            headers=auth(admin_token),
        )
        assert res.status_code in (200, 204), res.text

    def test_delete_sod_rule(self, client, admin_token, db):
        rule = self._create_rule(client, admin_token, name="rule-to-delete").json()
        rule_id = rule.get("id")
        res = client.delete(
            f"/api/v1/grc/sod-rules/{rule_id}",
            headers=auth(admin_token),
        )
        assert res.status_code in (200, 204), res.text

    def test_create_duplicate_rule_name(self, client, admin_token, db):
        self._create_rule(client, admin_token, name="dup-rule")
        res = self._create_rule(client, admin_token, name="dup-rule")
        # Should either succeed (names not unique) or return 409/422
        assert res.status_code in (200, 201, 409, 422)


# ── Violations ────────────────────────────────────────────────────────────────

class TestSodViolations:
    def test_list_violations_empty(self, client, admin_token, db):
        res = client.get("/api/v1/grc/violations", headers=auth(admin_token))
        assert res.status_code == 200
        assert isinstance(res.json(), list)

    def test_sod_check_no_violations(self, client, admin_token, db):
        res = client.get(
            "/api/v1/grc/sod-check",
            params={"user_id": "dev-test-id"},
            headers=auth(admin_token),
        )
        assert res.status_code == 200
        data = res.json()
        assert "violations" in data or isinstance(data, list)


# ── SoD Service unit tests ─────────────────────────────────────────────────────

class TestSodServiceUnit:
    """Direct service-layer tests for SoD business logic."""

    def test_record_sod_violation_creates_db_entry(self, db):
        from app.services.grc_sod import record_sod_violation
        from app.models.billing_reports import SodRule, SodViolation

        # Seed a SoD rule directly
        rule = SodRule(
            description="desc",
            module_a="invoices",
            action_a="crear",
            module_b="invoices",
            action_b="aprobar",
        )
        db.add(rule)
        db.flush()

        record_sod_violation(
            db=db,
            rule_id=rule.id,
            user_id="dev-test-id",
            role="employee",
            context_type="invoice",
            context_id="inv-123",
        )
        db.commit()

        violations = db.query(SodViolation).filter(SodViolation.rule_id == rule.id).all()
        assert len(violations) == 1
        assert violations[0].user_id == "dev-test-id"

    def test_self_approval_violation_detected(self, db):
        from app.services.grc_sod import record_self_approval_violation_for_request
        from app.models.billing_reports import SodRule

        # Seed a matching SoD rule
        rule = SodRule(
            description="creator cannot approve",
            module_a="approvals",
            action_a="crear",
            module_b="approvals",
            action_b="aprobar",
        )
        db.add(rule)
        db.flush()

        # Same user as creator → violation
        detected = record_self_approval_violation_for_request(
            db=db,
            entity_type="approvals",
            request_id="req-001",
            requested_by="dev-test-id",
            actor_id="dev-test-id",
            actor_role="employee",
        )
        db.commit()
        assert detected is True

    def test_no_self_approval_violation_when_different_user(self, db):
        from app.services.grc_sod import record_self_approval_violation_for_request
        from app.models.billing_reports import SodRule

        rule = SodRule(
            description="no cross-user violation",
            module_a="approvals",
            action_a="crear",
            module_b="approvals",
            action_b="aprobar",
        )
        db.add(rule)
        db.flush()

        detected = record_self_approval_violation_for_request(
            db=db,
            entity_type="approvals",
            request_id="req-002",
            requested_by="dev-test-id",
            actor_id="admin-test-id",   # Different user
            actor_role="admin",
        )
        assert detected is False


# ── Audit Log ─────────────────────────────────────────────────────────────────

class TestGRCAuditLog:
    def test_audit_log_empty_initially(self, client, admin_token, db):
        res = client.get("/api/v1/grc/audit-log", headers=auth(admin_token))
        assert res.status_code == 200
        assert isinstance(res.json(), list)

    def test_audit_log_service_entry(self, db):
        from app.services.grc_service import log_grc_entry
        from app.models.billing_reports import GrcAuditLog

        log_grc_entry(
            db=db,
            user_id="admin-test-id",
            action_type="permission_changed",
            resource_type="role_permission",
            resource_id="rp-001",
            detail={"role": "pm", "module": "invoices"},
            severity="warning",
        )
        db.commit()

        entries = db.query(GrcAuditLog).filter(
            GrcAuditLog.action_type == "permission_changed"
        ).all()
        assert len(entries) == 1
        assert entries[0].severity == "warning"
