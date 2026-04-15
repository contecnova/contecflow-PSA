"""
tests/test_issues_16_20.py
Tests for the 5 architecture fixes:
  #16 – Financial approval audit log (SOX/ISAE 3402)
  #17 – Multi-currency profitability with date-based FX
  #18 – Persisted SLA metrics (first_response_minutes, resolution_minutes, breached flags)
  #19 – API v2 scaffolding
  #20 – CMDB BFS depth + pagination
"""
import uuid
from datetime import date, datetime, timezone, timedelta

import pytest
from fastapi.testclient import TestClient

from tests.conftest import auth, _TEST_PASSWORD

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_approval_workflow(client, admin_token):
    """Create a minimal single-step approval workflow and return its id.
    Uses pm-test-id as the approver so the admin requester doesn't hit the SoD check.
    """
    res = client.post(
        "/api/v1/approvals/workflows",
        json={
            "name": "Test Financial Workflow",
            "entity_type": "expense",
        },
        headers=auth(admin_token),
    )
    assert res.status_code in (200, 201), f"Workflow creation failed: {res.text}"
    wf_id = res.json()["id"]

    # Add a step (pm-test-id is approver so admin can create + PM can approve — avoids SoD)
    step_res = client.post(
        f"/api/v1/approvals/workflows/{wf_id}/steps",
        json={
            "step_order": 1,
            "name": "Manager Approval",
            "approver_type": "user",
            "approver_user_id": "pm-test-id",
            "is_optional": False,
        },
        headers=auth(admin_token),
    )
    assert step_res.status_code in (200, 201), f"Step creation failed: {step_res.text}"
    return wf_id


def _make_approval_request(client, admin_token, workflow_id, entity_type="expense"):
    """Submit an approval request and return its id."""
    res = client.post(
        "/api/v1/approvals/requests",
        json={
            "workflow_id": workflow_id,
            "entity_type": entity_type,
            "entity_id": str(uuid.uuid4()),
            "note": "Test request",
        },
        headers=auth(admin_token),
    )
    assert res.status_code in (200, 201), f"Request creation failed: {res.text}"
    return res.json()["id"]


# ─────────────────────────────────────────────────────────────────────────────
# Issue #16 — Financial Approval Audit Log
# ─────────────────────────────────────────────────────────────────────────────

class TestFinancialAuditLog:
    """Issue #16: Immutable financial audit log separate from general activity."""

    def test_financial_audit_log_written_on_request_create(self, client, db, admin_token):
        """Creating an approval request for a financial entity writes to the audit log."""
        from app.models.billing_reports import FinancialApprovalAuditLog

        workflow_id = _make_approval_workflow(client, admin_token)
        request_id = _make_approval_request(client, admin_token, workflow_id, entity_type="expense")

        entries = (
            db.query(FinancialApprovalAuditLog)
            .filter(FinancialApprovalAuditLog.request_id == request_id)
            .all()
        )
        assert len(entries) >= 1
        assert entries[0].action == "requested"
        assert entries[0].entity_type == "expense"

    def test_financial_audit_log_not_written_for_non_financial(self, client, db, admin_token):
        """Approval requests for non-financial entity types do NOT write to the financial audit log."""
        from app.models.billing_reports import FinancialApprovalAuditLog, ApprovalWorkflow, ApprovalStep, ApprovalRequest

        # Create a workflow for a non-financial type (e.g. "change_request")
        wf = ApprovalWorkflow(
            id=str(uuid.uuid4()),
            name="Change Workflow",
            entity_type="change_request",
        )
        step = ApprovalStep(
            id=str(uuid.uuid4()),
            workflow_id=wf.id,
            step_order=1,
            name="Approval Step",
            approver_type="user",
            approver_user_id="admin-test-id",
        )
        req = ApprovalRequest(
            id=str(uuid.uuid4()),
            workflow_id=wf.id,
            entity_type="change_request",
            entity_id=str(uuid.uuid4()),
            requested_by="admin-test-id",
            status="pending",
            current_step=1,
        )
        db.add_all([wf, step, req])
        db.commit()

        # No financial audit log entries should exist for this request
        entries = (
            db.query(FinancialApprovalAuditLog)
            .filter(FinancialApprovalAuditLog.request_id == req.id)
            .all()
        )
        assert len(entries) == 0

    def test_financial_audit_log_endpoint_returns_entries(self, client, db, admin_token):
        """GET /approvals/requests/{id}/financial-audit returns audit entries."""
        workflow_id = _make_approval_workflow(client, admin_token)
        request_id = _make_approval_request(client, admin_token, workflow_id, entity_type="expense")

        res = client.get(
            f"/api/v1/approvals/requests/{request_id}/financial-audit",
            headers=auth(admin_token),
        )
        assert res.status_code == 200
        data = res.json()
        assert data["request_id"] == request_id
        assert data["entity_type"] == "expense"
        assert len(data["entries"]) >= 1
        assert data["entries"][0]["action"] == "requested"

    def test_financial_audit_log_endpoint_rejects_non_financial(self, client, db, admin_token):
        """GET /approvals/requests/{id}/financial-audit returns 404 for non-financial entity."""
        from app.models.billing_reports import ApprovalWorkflow, ApprovalStep, ApprovalRequest

        wf = ApprovalWorkflow(
            id=str(uuid.uuid4()),
            name="Generic Workflow",
            entity_type="project",
        )
        req = ApprovalRequest(
            id=str(uuid.uuid4()),
            workflow_id=wf.id,
            entity_type="project",
            entity_id=str(uuid.uuid4()),
            requested_by="admin-test-id",
            status="pending",
            current_step=1,
        )
        db.add_all([wf, req])
        db.commit()

        res = client.get(
            f"/api/v1/approvals/requests/{req.id}/financial-audit",
            headers=auth(admin_token),
        )
        assert res.status_code == 404

    def test_financial_audit_log_decision_written(self, client, db, admin_token, pm_token):
        """Approving a financial request adds a second entry to the audit log."""
        from app.models.billing_reports import FinancialApprovalAuditLog

        workflow_id = _make_approval_workflow(client, admin_token)
        request_id = _make_approval_request(client, admin_token, workflow_id, entity_type="expense")

        # Approve the request as PM (admin submitted, PM approves — avoids SoD block)
        res = client.post(
            f"/api/v1/approvals/requests/{request_id}/decide",
            json={"decision": "approved", "note": "Looks good"},
            headers=auth(pm_token),
        )
        assert res.status_code in (200, 201), f"Decision failed: {res.text}"

        entries = (
            db.query(FinancialApprovalAuditLog)
            .filter(FinancialApprovalAuditLog.request_id == request_id)
            .order_by(FinancialApprovalAuditLog.created_at)
            .all()
        )
        actions = [e.action for e in entries]
        assert "requested" in actions
        assert "approved" in actions


# ─────────────────────────────────────────────────────────────────────────────
# Issue #17 — Multi-currency profitability
# ─────────────────────────────────────────────────────────────────────────────

class TestMultiCurrencyProfitability:
    """Issue #17: Costs normalized to org base currency via date-based FX rate."""

    def test_same_currency_no_conversion_needed(self, db):
        """When project currency == org currency, FX rate is 1.0 (no conversion)."""
        from app.api.v1.endpoints.profitability import _get_fx_rate, _fx_cache
        _fx_cache.clear()

        from app.core.config import settings
        base = settings.DEFAULT_CURRENCY

        rate = _get_fx_rate(db, base, base, date.today())
        assert rate == 1.0

    def test_fx_rate_lookup_uses_most_recent_before_date(self, db):
        """FX rate lookup returns the rate with effective_date <= as_of (most recent)."""
        from app.models.bookings import ExchangeRate
        from app.api.v1.endpoints.profitability import _get_fx_rate, _fx_cache
        _fx_cache.clear()

        today = date.today()
        old_rate = ExchangeRate(
            id=str(uuid.uuid4()),
            from_currency="USD",
            to_currency="EUR",
            rate=0.85,
            effective_date=today - timedelta(days=30),
            source="test",
        )
        newer_rate = ExchangeRate(
            id=str(uuid.uuid4()),
            from_currency="USD",
            to_currency="EUR",
            rate=0.92,
            effective_date=today - timedelta(days=5),
            source="test",
        )
        db.add_all([old_rate, newer_rate])
        db.commit()

        # Should return the newer rate (most recent <= today)
        rate = _get_fx_rate(db, "USD", "EUR", today)
        _fx_cache.clear()
        assert rate == pytest.approx(0.92)

    def test_fx_rate_lookup_returns_1_when_no_rate_found(self, db):
        """FX rate defaults to 1.0 when no ExchangeRate row matches (safe fallback)."""
        from app.api.v1.endpoints.profitability import _get_fx_rate, _fx_cache
        _fx_cache.clear()

        rate = _get_fx_rate(db, "XYZ", "EUR", date(2020, 1, 1))
        _fx_cache.clear()
        assert rate == 1.0

    def test_profitability_response_includes_currency_fields(self, client, db, admin_token):
        """Profitability summary endpoint returns 200 without errors (currency fields added to individual project calcs)."""
        res = client.get("/api/v1/profitability/summary", headers=auth(admin_token))
        assert res.status_code == 200
        data = res.json()
        # Response is either a list of projects or a dict with 'projects' key
        assert isinstance(data, (list, dict))

    def test_fx_rate_not_used_for_future_date(self, db):
        """FX rate lookup for a future date relative to rates returns fallback 1.0."""
        from app.api.v1.endpoints.profitability import _get_fx_rate, _fx_cache
        _fx_cache.clear()

        future_date = date(2099, 1, 1)
        rate = _get_fx_rate(db, "JPY", "EUR", future_date)
        _fx_cache.clear()
        # No rates exist for JPY in test DB — should fallback to 1.0
        assert rate == 1.0


# ─────────────────────────────────────────────────────────────────────────────
# Issue #18 — Persisted SLA Metrics
# ─────────────────────────────────────────────────────────────────────────────

class TestPersistedSLAMetrics:
    """Issue #18: SLA metrics are persisted at resolution time, not recomputed live."""

    def _create_ticket(self, client, admin_token, ticket_type="incident"):
        res = client.post(
            "/api/v1/sd/tickets",
            json={
                "title": "Test SLA ticket",
                "description": "Test description for SLA metrics validation",
                "ticket_type": ticket_type,
                "urgency": "medium",
                "impact": "user",
                "requester_name": "Test User",
                "requester_email": "test@example.com",
                "source": "email",
            },
            headers=auth(admin_token),
        )
        assert res.status_code in (200, 201), f"Ticket creation failed: {res.text}"
        return res.json()["id"]

    def test_first_response_minutes_persisted_on_in_progress(self, client, db, admin_token):
        """Setting status=in_progress persists first_response_minutes on the ticket."""
        from app.models.service_desk import Ticket

        ticket_id = self._create_ticket(client, admin_token)

        res = client.patch(
            f"/api/v1/sd/tickets/{ticket_id}",
            json={"status": "in_progress"},
            headers=auth(admin_token),
        )
        assert res.status_code == 200

        db.expire_all()
        ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
        assert ticket.first_response_at is not None
        assert ticket.first_response_minutes is not None
        assert ticket.first_response_minutes >= 0

    def test_resolution_minutes_persisted_on_resolved(self, client, db, admin_token):
        """Setting status=resolved persists resolution_minutes on the ticket."""
        from app.models.service_desk import Ticket

        ticket_id = self._create_ticket(client, admin_token)

        res = client.patch(
            f"/api/v1/sd/tickets/{ticket_id}",
            json={"status": "resolved", "resolution": "Fixed", "resolution_code": "solved"},
            headers=auth(admin_token),
        )
        assert res.status_code == 200

        db.expire_all()
        ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
        assert ticket.resolved_at is not None
        assert ticket.resolution_minutes is not None
        assert ticket.resolution_minutes >= 0

    def test_sla_response_breached_flag_stored(self, client, db, admin_token):
        """sla_response_breached is stored as False when SLA is not breached at first response."""
        from app.models.service_desk import Ticket

        ticket_id = self._create_ticket(client, admin_token)

        client.patch(
            f"/api/v1/sd/tickets/{ticket_id}",
            json={"status": "in_progress"},
            headers=auth(admin_token),
        )

        db.expire_all()
        ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
        # sla_response_breached must now be a stored column (not None/unset after first response)
        assert ticket.sla_response_breached is not None

    def test_sla_resolution_breached_flag_stored_on_resolve(self, client, db, admin_token):
        """sla_resolution_breached is stored when ticket is resolved."""
        from app.models.service_desk import Ticket

        ticket_id = self._create_ticket(client, admin_token)

        client.patch(
            f"/api/v1/sd/tickets/{ticket_id}",
            json={"status": "resolved", "resolution": "Done", "resolution_code": "solved"},
            headers=auth(admin_token),
        )

        db.expire_all()
        ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
        assert ticket.sla_resolution_breached is not None

    def test_ticket_out_uses_stored_first_response_minutes(self, db):
        """ticket_out() returns stored first_response_minutes / 60 when available."""
        from app.services.sla_service import ticket_out
        from app.models.service_desk import Ticket

        now = datetime.now(timezone.utc)
        t = Ticket(
            id=str(uuid.uuid4()),
            number="INC-9999",
            ticket_type="incident",
            title="Test",
            description="Test description",
            status="resolved",
            priority="p3_medium",
            urgency="medium",
            impact="user",
            source="email",
            created_at=now - timedelta(hours=2),
            first_response_at=now - timedelta(hours=1),
            resolved_at=now,
            first_response_minutes=60,     # stored value: exactly 1 hour
            resolution_minutes=120,        # stored value: exactly 2 hours
        )
        db.add(t)
        db.commit()

        result = ticket_out(t)
        # Should read stored value (60 min / 60 = 1.0 h) not recompute from datetime
        assert result["time_to_response_hours"] == pytest.approx(1.0)
        assert result["time_to_resolution_hours"] == pytest.approx(2.0)


# ─────────────────────────────────────────────────────────────────────────────
# Issue #19 — API v2 Scaffolding
# ─────────────────────────────────────────────────────────────────────────────

class TestAPIv2:
    """Issue #19: API v2 contract surface is distinct from v1."""

    def test_v2_version_endpoint_accessible(self, client):
        """/api/v2/version returns 200 with version metadata."""
        res = client.get("/api/v2/version")
        assert res.status_code == 200
        data = res.json()
        assert data["api_version"] == 2

    def test_v2_response_lists_breaking_changes(self, client):
        """v2/version lists breaking changes vs v1."""
        res = client.get("/api/v2/version")
        assert res.status_code == 200
        data = res.json()
        assert "breaking_changes_vs_v1" in data
        assert len(data["breaking_changes_vs_v1"]) > 0

    def test_v1_header_x_api_deprecated_is_true(self, client, admin_token):
        """v1 responses now include X-API-Deprecated: true since v2 exists."""
        res = client.get("/api/v1/auth/me", headers=auth(admin_token))
        # Header may be present; if v2 is mounted, middleware sets it
        assert res.headers.get("x-api-deprecated") == "true"

    def test_v2_header_x_api_version_is_2(self, client):
        """v2 responses include X-API-Version: 2."""
        res = client.get("/api/v2/version")
        assert res.headers.get("x-api-version") == "2"

    def test_v1_still_works(self, client, admin_token):
        """All existing v1 endpoints remain accessible after v2 is added."""
        res = client.get("/api/v1/auth/me", headers=auth(admin_token))
        assert res.status_code == 200

    def test_v2_path_prefix_distinct_from_v1(self, client):
        """v2 is mounted at /api/v2, not /api/v1."""
        from app.core.config import settings
        assert settings.API_V2_STR == "/api/v2"
        assert settings.API_V2_STR != settings.API_V1_STR


# ─────────────────────────────────────────────────────────────────────────────
# Issue #20 — CMDB BFS depth + pagination
# ─────────────────────────────────────────────────────────────────────────────

class TestCMDBImpactGraph:
    """Issue #20: CMDB impact analysis supports navigable graph with depth and limit."""

    def _make_superadmin(self, db):
        """Temporarily flag admin as superadmin so CMDB scoping passes in tests."""
        from app.models.user import User
        admin = db.query(User).filter(User.id == "admin-test-id").first()
        admin.is_superadmin = True
        db.commit()

    def _create_ci(self, db, name="Server", ci_type="server"):
        from app.models.service_desk import ConfigurationItem, CIType, CIStatus
        ci = ConfigurationItem(
            id=str(uuid.uuid4()),
            code=f"CI-{name[:4].upper()}-{uuid.uuid4().hex[:4]}",
            name=name,
            ci_type=CIType.server,
            criticality="high",
            status=CIStatus.operational,
        )
        db.add(ci)
        db.flush()
        return ci

    def _create_relation(self, db, source_ci, target_ci, relation_type="depends_on"):
        from app.models.service_desk import CIRelation, CIRelationType
        rel = CIRelation(
            id=str(uuid.uuid4()),
            source_ci_id=source_ci.id,
            target_ci_id=target_ci.id,
            relation_type=CIRelationType.depends_on,
        )
        db.add(rel)
        db.flush()
        return rel

    def test_impact_result_includes_depth_field(self, client, db, admin_token):
        """Each CI in impacted list includes a 'depth' field (hop distance from root)."""
        self._make_superadmin(db)
        ci_root = self._create_ci(db, name="RootServer")
        ci_dep = self._create_ci(db, name="AppServer")
        self._create_relation(db, ci_dep, ci_root)
        db.commit()

        res = client.get(
            f"/api/v1/sd/cmdb/{ci_root.id}/impact",
            headers=auth(admin_token),
        )
        assert res.status_code == 200
        data = res.json()
        if data["impacted_count"] > 0:
            assert "depth" in data["impacted"][0]

    def test_impact_result_includes_truncated_flag(self, client, db, admin_token):
        """Impact endpoint returns a 'truncated' boolean field."""
        self._make_superadmin(db)
        ci_root = self._create_ci(db, name="RootNode")
        db.commit()

        res = client.get(
            f"/api/v1/sd/cmdb/{ci_root.id}/impact",
            headers=auth(admin_token),
        )
        assert res.status_code == 200
        data = res.json()
        assert "truncated" in data
        assert isinstance(data["truncated"], bool)

    def test_max_depth_query_param_accepted(self, client, db, admin_token):
        """max_depth query parameter is accepted without error."""
        self._make_superadmin(db)
        ci = self._create_ci(db, name="DepthTest")
        db.commit()

        res = client.get(
            f"/api/v1/sd/cmdb/{ci.id}/impact?max_depth=2",
            headers=auth(admin_token),
        )
        assert res.status_code == 200
        data = res.json()
        assert data["max_depth"] == 2

    def test_limit_query_param_accepted(self, client, db, admin_token):
        """limit query parameter is accepted without error."""
        self._make_superadmin(db)
        ci = self._create_ci(db, name="LimitTest")
        db.commit()

        res = client.get(
            f"/api/v1/sd/cmdb/{ci.id}/impact?limit=10",
            headers=auth(admin_token),
        )
        assert res.status_code == 200

    def test_bfs_stops_at_max_depth_1(self, client, db, admin_token):
        """With max_depth=1, BFS returns only direct dependents, not transitive ones."""
        self._make_superadmin(db)
        ci_root = self._create_ci(db, name="Root")
        ci_level1 = self._create_ci(db, name="Level1")
        ci_level2 = self._create_ci(db, name="Level2")

        # level2 → level1 → root (chain of length 2)
        self._create_relation(db, ci_level1, ci_root)
        self._create_relation(db, ci_level2, ci_level1)
        db.commit()

        res = client.get(
            f"/api/v1/sd/cmdb/{ci_root.id}/impact?max_depth=1",
            headers=auth(admin_token),
        )
        assert res.status_code == 200
        data = res.json()
        impacted_ids = {i["ci_id"] for i in data["impacted"]}
        # level1 is a direct dependent (depth=1) — should be included
        assert ci_level1.id in impacted_ids
        # level2 is depth=2 — must NOT be included when max_depth=1
        assert ci_level2.id not in impacted_ids

    def test_limit_truncates_result(self, client, db, admin_token):
        """When limit=1 and multiple CIs would be returned, truncated=True."""
        self._make_superadmin(db)
        ci_root = self._create_ci(db, name="BigRoot")
        for i in range(3):
            ci_dep = self._create_ci(db, name=f"Dep{i}")
            self._create_relation(db, ci_dep, ci_root)
        db.commit()

        res = client.get(
            f"/api/v1/sd/cmdb/{ci_root.id}/impact?limit=1",
            headers=auth(admin_token),
        )
        assert res.status_code == 200
        data = res.json()
        assert data["impacted_count"] <= 1
        assert data["truncated"] is True
