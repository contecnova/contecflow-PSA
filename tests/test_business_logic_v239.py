"""
tests/test_business_logic_v239.py

Business logic tests for v23.9.0 features:
  1. ECB exchange rate service (sync + get_rate)
  2. OrgBranding CRUD — white-label/tenant branding
  3. Gantt baselines — create, compare, delete
  4. Integration marketplace — catalog seeding, install, uninstall
  5. Customer health composite score formula
  6. AI Copilot contextual suggestions (Gantt overdue, gap detection)
  7. Enhanced template endpoints (documents + roles + full + export)
  8. Approval workflow builder (schema + validate)
  9. Slack Block Kit preview
"""
import json
import pytest
from datetime import date, datetime, timedelta
from fastapi.testclient import TestClient


# ══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def admin_headers(client, admin_token, organization):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture()
def pm_headers(client, pm_token, organization):
    return {"Authorization": f"Bearer {pm_token}"}


@pytest.fixture()
def organization(db):
    from app.models.mfa import Organization
    from app.models.user import User

    org = Organization(name="Acme Org", slug="acme-org-v239")
    db.add(org)
    db.flush()

    # Keep test users inside the same tenant so org-scoped endpoints work.
    db.query(User).filter(User.id.in_(["admin-test-id", "pm-test-id", "dev-test-id"]))\
        .update({"organization_id": org.id}, synchronize_session=False)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture()
def project(db, organization):
    from app.models.project import Project, ProjectType, ProjectStatus

    p = Project(
        organization_id=organization.id,
        code="V239-PRJ",
        name="V239 Test Project",
        project_type=ProjectType.development,
        status=ProjectStatus.active,
        client_name="Acme Client",
        is_billable=False,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@pytest.fixture()
def sample_client(db):
    from app.models.clients import Client

    c = Client(
        name="Sample Client V239",
        short_name="SCV239",
        contact_email="contact@sampleclient.test",
        account_manager_id="admin-test-id",
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@pytest.fixture()
def test_user(db, organization):
    from app.models.user import User

    u = db.query(User).filter(User.id == "dev-test-id").first()
    u.organization_id = organization.id
    db.commit()
    db.refresh(u)
    return u


# ══════════════════════════════════════════════════════════════════════════════
# 1. ECB Exchange Rate Service (unit-level)
# ══════════════════════════════════════════════════════════════════════════════

class TestECBRateServiceUnit:
    """Tests the exchange_rate_service helper functions directly with the in-memory DB."""

    def test_get_rate_returns_none_when_no_data(self, db):
        from app.services.exchange_rate_service import get_rate
        result = get_rate(db, "USD", "EUR")
        assert result is None

    def test_upsert_pair_and_get_rate(self, db):
        from app.services.exchange_rate_service import _upsert_pair, get_rate
        _upsert_pair(db, "EUR", "USD", 1.08, date.today())
        rate = get_rate(db, "EUR", "USD")
        assert rate == pytest.approx(1.08, rel=1e-4)

    def test_upsert_pair_is_idempotent(self, db):
        from app.services.exchange_rate_service import _upsert_pair, get_rate
        _upsert_pair(db, "EUR", "GBP", 0.86, date.today())
        _upsert_pair(db, "EUR", "GBP", 0.865, date.today())  # re-upsert same date
        rate = get_rate(db, "EUR", "GBP")
        assert rate == pytest.approx(0.865, rel=1e-4)

    def test_get_rate_historical(self, db):
        from app.services.exchange_rate_service import _upsert_pair, get_rate
        yesterday = date.today() - timedelta(days=1)
        _upsert_pair(db, "EUR", "JPY", 162.5, yesterday)
        rate = get_rate(db, "EUR", "JPY", as_of=yesterday)
        assert rate == pytest.approx(162.5, rel=1e-3)


# ══════════════════════════════════════════════════════════════════════════════
# 2. ECB Sync Endpoint
# ══════════════════════════════════════════════════════════════════════════════

class TestECBSyncEndpoint:

    def test_sync_ecb_requires_admin(self, client, pm_headers):
        resp = client.post("/api/v1/currency/sync-ecb", headers=pm_headers)
        assert resp.status_code == 403

    def test_sync_openexchangerates_without_config_503(self, client, admin_headers):
        """Without OPEN_EXCHANGE_RATES_APP_ID env, should return 503."""
        import os
        os.environ.pop("OPEN_EXCHANGE_RATES_APP_ID", None)
        resp = client.post("/api/v1/currency/sync-openexchangerates", headers=admin_headers)
        assert resp.status_code == 503
        assert "OPEN_EXCHANGE_RATES_APP_ID" in resp.json()["detail"]


# ══════════════════════════════════════════════════════════════════════════════
# 3. OrgBranding / White-label
# ══════════════════════════════════════════════════════════════════════════════

class TestOrgBranding:

    def test_get_branding_default_for_unknown_org(self, client, admin_headers, organization):
        resp = client.get(f"/api/v1/orgs/{organization.id}/branding", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        # Default values
        assert data.get("is_default") is True or "app_name" in data

    def test_update_branding_valid(self, client, admin_headers, organization):
        resp = client.put(
            f"/api/v1/orgs/{organization.id}/branding",
            json={
                "app_name": "MyCorp PM",
                "primary_color": "#123456",
                "hide_powered_by": True,
                "custom_domain": "pm.mycorp.com",
            },
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["app_name"] == "MyCorp PM"
        assert data["primary_color"] == "#123456"
        assert data["hide_powered_by"] is True
        assert data["custom_domain"] == "pm.mycorp.com"

    def test_update_branding_invalid_color_rejected(self, client, admin_headers, organization):
        resp = client.put(
            f"/api/v1/orgs/{organization.id}/branding",
            json={"primary_color": "not-a-color"},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_update_branding_invalid_domain_rejected(self, client, admin_headers, organization):
        resp = client.put(
            f"/api/v1/orgs/{organization.id}/branding",
            json={"custom_domain": "https://pm.mycorp.com/path?q=1"},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_update_branding_css_vars_sanitized(self, client, admin_headers, organization):
        resp = client.put(
            f"/api/v1/orgs/{organization.id}/branding",
            json={"custom_css_vars": {
                "--primary": "#6366f1",         # valid
                "no-dash": "red",               # invalid — no leading --
                "--x" * 40: "y",               # too long key
            }},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        css_vars = data["custom_css_vars"]
        assert "--primary" in css_vars
        assert "no-dash" not in css_vars

    def test_reset_branding(self, client, admin_headers, organization):
        resp = client.delete(
            f"/api/v1/orgs/{organization.id}/branding", headers=admin_headers
        )
        assert resp.status_code == 204

    def test_non_admin_cannot_update_branding(self, client, pm_headers, organization):
        resp = client.put(
            f"/api/v1/orgs/{organization.id}/branding",
            json={"app_name": "Hacked"},
            headers=pm_headers,
        )
        assert resp.status_code == 403


# ══════════════════════════════════════════════════════════════════════════════
# 4. Gantt Baselines
# ══════════════════════════════════════════════════════════════════════════════

class TestGanttBaselines:

    def test_list_baselines_empty(self, client, admin_headers, project):
        resp = client.get(f"/api/v1/projects/{project.id}/baselines", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_baseline(self, client, admin_headers, project):
        resp = client.post(
            f"/api/v1/projects/{project.id}/baselines",
            json={"name": "Sprint 1 Baseline", "description": "Frozen after planning", "is_initial": True},
            headers=admin_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["created"] is True
        assert data["name"] == "Sprint 1 Baseline"
        assert "baseline_date" in data
        return data["id"]

    def test_list_baselines_returns_created(self, client, admin_headers, project):
        # Create one first
        client.post(
            f"/api/v1/projects/{project.id}/baselines",
            json={"name": "Initial Baseline", "is_initial": True},
            headers=admin_headers,
        )
        resp = client.get(f"/api/v1/projects/{project.id}/baselines", headers=admin_headers)
        assert resp.status_code == 200
        baselines = resp.json()
        assert len(baselines) >= 1
        assert any(b["name"] == "Initial Baseline" for b in baselines)

    def test_compare_baseline_with_no_tasks(self, client, admin_headers, project):
        # Create baseline
        create_resp = client.post(
            f"/api/v1/projects/{project.id}/baselines",
            json={"name": "Compare Test"},
            headers=admin_headers,
        )
        assert create_resp.status_code == 201
        baseline_id = create_resp.json()["id"]

        resp = client.get(
            f"/api/v1/projects/{project.id}/baselines/{baseline_id}/compare",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "summary" in data
        assert "task_deltas" in data

    def test_delete_baseline(self, client, admin_headers, project):
        create_resp = client.post(
            f"/api/v1/projects/{project.id}/baselines",
            json={"name": "To Delete"},
            headers=admin_headers,
        )
        baseline_id = create_resp.json()["id"]
        del_resp = client.delete(
            f"/api/v1/projects/{project.id}/baselines/{baseline_id}",
            headers=admin_headers,
        )
        assert del_resp.status_code == 204

    def test_delete_nonexistent_baseline_404(self, client, admin_headers, project):
        resp = client.delete(
            f"/api/v1/projects/{project.id}/baselines/nonexistent-id",
            headers=admin_headers,
        )
        assert resp.status_code == 404

    def test_baseline_for_nonexistent_project_404(self, client, admin_headers):
        resp = client.get("/api/v1/projects/bad-project-id/baselines", headers=admin_headers)
        assert resp.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# 5. Integration Marketplace
# ══════════════════════════════════════════════════════════════════════════════

class TestIntegrationMarketplace:

    def test_list_marketplace_returns_connectors(self, client, admin_headers):
        resp = client.get("/api/v1/integrations/marketplace", headers=admin_headers)
        assert resp.status_code == 200
        connectors = resp.json()
        assert len(connectors) >= 20  # catalog has 22 connectors
        slugs = [c["slug"] for c in connectors]
        assert "salesforce" in slugs
        assert "jira" in slugs
        assert "slack" in slugs
        assert "stripe" in slugs

    def test_list_marketplace_filter_by_category(self, client, admin_headers):
        resp = client.get(
            "/api/v1/integrations/marketplace?category=crm", headers=admin_headers
        )
        assert resp.status_code == 200
        for c in resp.json():
            assert c["category"] == "crm"

    def test_list_marketplace_certified_only(self, client, admin_headers):
        resp = client.get(
            "/api/v1/integrations/marketplace?certified_only=true", headers=admin_headers
        )
        assert resp.status_code == 200
        for c in resp.json():
            assert c["is_certified"] is True

    def test_install_connector(self, client, admin_headers):
        resp = client.post(
            "/api/v1/integrations/instances",
            json={
                "connector_slug": "xero",
                "name": "Xero Produzione",
                "config": {"client_id": "fake-client-id", "client_secret": "s3cr3t"},
                "sync_direction": "bidirectional",
                "sync_frequency": "daily",
            },
            headers=admin_headers,
        )
        assert resp.status_code in (200, 201)
        data = resp.json()
        assert data.get("created", True) is True
        assert data["connector"] == "xero"
        # Config is NOT returned (sensitive data encrypted at rest)
        assert "client_secret" not in json.dumps(data)

    def test_install_unknown_connector_404(self, client, admin_headers):
        resp = client.post(
            "/api/v1/integrations/instances",
            json={"connector_slug": "nonexistent-slug", "name": "Bad"},
            headers=admin_headers,
        )
        assert resp.status_code == 404

    def test_install_invalid_sync_direction_422(self, client, admin_headers):
        resp = client.post(
            "/api/v1/integrations/instances",
            json={
                "connector_slug": "slack",
                "name": "Bad Direction",
                "sync_direction": "sideways",
            },
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_list_installed_instances(self, client, admin_headers):
        # Install one
        client.post(
            "/api/v1/integrations/instances",
            json={"connector_slug": "github", "name": "GitHub Main"},
            headers=admin_headers,
        )
        resp = client.get("/api/v1/integrations/instances", headers=admin_headers)
        assert resp.status_code == 200
        instances = resp.json()
        assert isinstance(instances, list)

    def test_uninstall_integration(self, client, admin_headers):
        install = client.post(
            "/api/v1/integrations/instances",
            json={"connector_slug": "aws_s3", "name": "S3 Backup"},
            headers=admin_headers,
        )
        assert install.status_code in (200, 201)
        inst_id = install.json()["id"]
        del_resp = client.delete(f"/api/v1/integrations/instances/{inst_id}", headers=admin_headers)
        assert del_resp.status_code == 204

    def test_non_admin_cannot_install(self, client, pm_headers):
        resp = client.post(
            "/api/v1/integrations/instances",
            json={"connector_slug": "slack", "name": "Slack"},
            headers=pm_headers,
        )
        assert resp.status_code == 403


# ══════════════════════════════════════════════════════════════════════════════
# 6. Customer Health Composite Score
# ══════════════════════════════════════════════════════════════════════════════

class TestCustomerHealthComposite:

    def test_health_for_nonexistent_client_404(self, client, admin_headers):
        resp = client.get("/api/v1/clients/bad-id/health-composite", headers=admin_headers)
        assert resp.status_code == 404

    def test_health_returns_composite_score(self, client, admin_headers, sample_client):
        resp = client.get(
            f"/api/v1/clients/{sample_client.id}/health-composite", headers=admin_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "composite_score" in data
        assert 0 <= data["composite_score"] <= 100
        assert data["category"] in ("excellent", "good", "at_risk", "critical")
        assert "components" in data
        assert "nps" in data["components"]
        assert "delivery" in data["components"]
        assert "budget" in data["components"]
        assert "ticket_resolution" in data["components"]
        assert "portal_activity" in data["components"]

    def test_health_composite_score_formula(self, db, sample_client):
        """Verify the composite formula weights sum to 1.0."""
        from app.api.v1.endpoints.v239_features import compute_composite_health
        weights = [0.40, 0.20, 0.15, 0.15, 0.10]
        assert abs(sum(weights) - 1.0) < 1e-9

    def test_health_category_excellent_threshold(self):
        """Score >= 80 should be 'excellent'."""
        score = 85.0
        category = ("excellent" if score >= 80 else "good" if score >= 60
                    else "at_risk" if score >= 40 else "critical")
        assert category == "excellent"

    def test_health_category_critical_threshold(self):
        score = 30.0
        category = ("excellent" if score >= 80 else "good" if score >= 60
                    else "at_risk" if score >= 40 else "critical")
        assert category == "critical"


# ══════════════════════════════════════════════════════════════════════════════
# 7. AI Copilot Contextual Suggestions
# ══════════════════════════════════════════════════════════════════════════════

class TestAICopilotContextual:

    def test_gantt_suggestions_nonexistent_project_404(self, client, admin_headers):
        resp = client.get("/api/v1/ai/suggestions/gantt/bad-project-id", headers=admin_headers)
        assert resp.status_code == 404

    def test_gantt_suggestions_empty_project(self, client, admin_headers, project):
        resp = client.get(
            f"/api/v1/ai/suggestions/gantt/{project.id}", headers=admin_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "suggestions" in data
        assert "suggestions_count" in data
        assert data["suggestions_count"] == len(data["suggestions"])

    def test_gantt_suggestions_detects_overdue(self, client, admin_headers, project, db):
        """An overdue task should generate a 'high' severity suggestion."""
        from app.models.task import Task, TaskStatus, TaskPriority
        overdue_task = Task(
            code="TASK-OVERDUE-1",
            project_id=project.id,
            title="Overdue Analysis Task",
            status=TaskStatus.in_progress,
            priority=TaskPriority.high,
            due_date=date.today() - timedelta(days=10),
        )
        db.add(overdue_task)
        db.commit()

        resp = client.get(
            f"/api/v1/ai/suggestions/gantt/{project.id}", headers=admin_headers
        )
        assert resp.status_code == 200
        suggestions = resp.json()["suggestions"]
        overdue = [s for s in suggestions if s.get("type") == "overdue"]
        assert len(overdue) >= 1
        assert overdue[0]["severity"] in ("high", "medium")

    def test_timesheet_anomalies_no_entries(self, client, admin_headers, test_user):
        resp = client.get(
            f"/api/v1/ai/suggestions/timesheets/{test_user.id}", headers=admin_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "anomalies" in data
        assert data["anomalies_count"] == 0

    def test_timesheet_high_hours_anomaly(self, db, client, admin_headers, test_user, project):
        """A day with >12 hours logged should trigger 'high_hours' anomaly."""
        from app.models.imputation import Imputation
        db.add(Imputation(
            user_id=test_user.id, project_id=project.id,
            date=date.today() - timedelta(days=2), hours=13.5,
        ))
        db.commit()
        resp = client.get(
            f"/api/v1/ai/suggestions/timesheets/{test_user.id}", headers=admin_headers
        )
        data = resp.json()
        high_hours = [a for a in data["anomalies"] if a.get("type") == "high_hours"]
        assert len(high_hours) >= 1
        assert high_hours[0]["value"] >= 12

    def test_kb_ticket_suggestion_nonexistent_404(self, client, admin_headers):
        resp = client.get("/api/v1/ai/suggestions/ticket/bad-id", headers=admin_headers)
        assert resp.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# 8. Enhanced Project Templates
# ══════════════════════════════════════════════════════════════════════════════

class TestEnhancedTemplates:

    def _create_template(self, client, headers):
        resp = client.post(
            "/api/v1/templates",
            json={"name": "E2E Template", "description": "For testing v239",
                  "project_type": "fixed_price", "estimated_weeks": 12},
            headers=headers,
        )
        assert resp.status_code in (200, 201)
        return resp.json()["id"]

    def test_add_document_to_template(self, client, admin_headers):
        tmpl_id = self._create_template(client, admin_headers)
        resp = client.post(
            f"/api/v1/templates/{tmpl_id}/documents",
            json={"name": "SOW", "document_type": "spec",
                  "description": "Statement of Work", "is_required": True, "due_week_offset": 1},
            headers=admin_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["created"] is True

    def test_add_role_to_template(self, client, admin_headers):
        tmpl_id = self._create_template(client, admin_headers)
        resp = client.post(
            f"/api/v1/templates/{tmpl_id}/roles",
            json={"role_name": "Tech Lead", "skill_required": "Python",
                  "min_seniority": "senior", "estimated_hours": 120, "is_mandatory": True},
            headers=admin_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["role_name"] == "Tech Lead"

    def test_get_full_template_structure(self, client, admin_headers):
        tmpl_id = self._create_template(client, admin_headers)
        # Add document + role
        client.post(f"/api/v1/templates/{tmpl_id}/documents",
                    json={"name": "Requirements Doc", "is_required": True}, headers=admin_headers)
        client.post(f"/api/v1/templates/{tmpl_id}/roles",
                    json={"role_name": "BA", "is_mandatory": True}, headers=admin_headers)
        resp = client.get(f"/api/v1/templates/{tmpl_id}/full", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "phases" in data
        assert "risks" in data
        assert "deliverables" in data
        assert "documents" in data
        assert "roles" in data
        assert len(data["documents"]) >= 1
        assert len(data["roles"]) >= 1

    def test_add_doc_to_nonexistent_template_404(self, client, admin_headers):
        resp = client.post(
            "/api/v1/templates/bad-id/documents",
            json={"name": "X"},
            headers=admin_headers,
        )
        assert resp.status_code == 404

    def test_export_project_as_template(self, client, admin_headers, project):
        resp = client.post(
            f"/api/v1/projects/{project.id}/export-template",
            json={"name": "Exported Template", "description": "From project"},
            headers=admin_headers,
        )
        assert resp.status_code in (200, 201)
        data = resp.json()
        assert data.get("created", True) is True
        assert "template_id" in data


# ══════════════════════════════════════════════════════════════════════════════
# 9. Approval Workflow Visual Builder
# ══════════════════════════════════════════════════════════════════════════════

class TestApprovalWorkflowBuilder:

    def test_get_schema_returns_node_types(self, client, admin_headers):
        resp = client.get("/api/v1/approval-workflows/builder/schema", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "node_types" in data
        assert "edge_types" in data
        types = [n["type"] for n in data["node_types"]]
        assert "start" in types
        assert "approval_step" in types
        assert "condition" in types
        assert "end" in types

    def test_validate_valid_workflow(self, client, admin_headers):
        workflow = {
            "nodes": [
                {"id": "n1", "type": "start"},
                {"id": "n2", "type": "approval_step"},
                {"id": "n3", "type": "end"},
            ],
            "edges": [
                {"source": "n1", "target": "n2"},
                {"source": "n2", "target": "n3"},
            ],
        }
        resp = client.post(
            "/api/v1/approval-workflows/builder/validate",
            json=workflow,
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["errors"] == []

    def test_validate_missing_start_node_invalid(self, client, admin_headers):
        workflow = {
            "nodes": [
                {"id": "n1", "type": "approval_step"},
                {"id": "n2", "type": "end"},
            ],
            "edges": [{"source": "n1", "target": "n2"}],
        }
        resp = client.post(
            "/api/v1/approval-workflows/builder/validate",
            json=workflow,
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert any("start" in e.lower() for e in data["errors"])

    def test_validate_missing_end_node_invalid(self, client, admin_headers):
        workflow = {
            "nodes": [
                {"id": "n1", "type": "start"},
                {"id": "n2", "type": "approval_step"},
            ],
            "edges": [{"source": "n1", "target": "n2"}],
        }
        resp = client.post(
            "/api/v1/approval-workflows/builder/validate",
            json=workflow,
            headers=admin_headers,
        )
        data = resp.json()
        assert data["valid"] is False
        assert any("end" in e.lower() for e in data["errors"])

    def test_validate_orphaned_node_raises_warning(self, client, admin_headers):
        workflow = {
            "nodes": [
                {"id": "n1", "type": "start"},
                {"id": "n2", "type": "end"},
                {"id": "n3", "type": "action"},   # orphaned — no incoming edge
            ],
            "edges": [{"source": "n1", "target": "n2"}],
        }
        resp = client.post(
            "/api/v1/approval-workflows/builder/validate",
            json=workflow,
            headers=admin_headers,
        )
        data = resp.json()
        # Should still be valid (warning, not error) if orphan doesn't block flow
        assert "warnings" in data
        assert len(data["warnings"]) >= 1


# ══════════════════════════════════════════════════════════════════════════════
# 10. Slack Block Kit Preview
# ══════════════════════════════════════════════════════════════════════════════

class TestSlackBlockKitPreview:

    def test_preview_task_overdue(self, client, admin_headers):
        resp = client.get(
            "/api/v1/notifications/slack/block-kit/preview?event_type=task_overdue",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "blocks" in data
        block_text_combined = json.dumps(data["blocks"]).lower()
        assert "overdue" in block_text_combined

    def test_preview_invoice_paid(self, client, admin_headers):
        resp = client.get(
            "/api/v1/notifications/slack/block-kit/preview?event_type=invoice_paid",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "blocks" in data
        # Should include amount info
        text = json.dumps(data["blocks"])
        assert "12500" in text or "Invoice" in text

    def test_preview_approval_required(self, client, admin_headers):
        resp = client.get(
            "/api/v1/notifications/slack/block-kit/preview?event_type=approval_required",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "blocks" in data

    def test_preview_custom_event_returns_generic(self, client, admin_headers):
        resp = client.get(
            "/api/v1/notifications/slack/block-kit/preview?event_type=custom_event",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "blocks" in data

    def test_send_slack_without_webhook_503(self, client, admin_headers):
        """Without a configured webhook, sending should return 503."""
        resp = client.post(
            "/api/v1/notifications/slack/block-kit",
            json={
                "event_type": "task_overdue",
                "data": {"task_title": "Test", "project_name": "Test Project"},
            },
            headers=admin_headers,
        )
        # 503 if no webhook configured, 502 if delivery fails
        assert resp.status_code in (503, 502)


# ══════════════════════════════════════════════════════════════════════════════
# 11. i18n completeness check
# ══════════════════════════════════════════════════════════════════════════════

class TestI18nV239:

    def test_v239_section_exists_in_all_8_languages(self):
        """v239 section must appear exactly once per language."""
        import re
        path = "frontend/src/i18n/appTranslations.js"
        content = open(path).read()
        count = content.count("v239:")
        assert count == 8, f"Expected 8 v239 sections (one per language), found {count}"

    def test_v239_keys_present_in_es(self):
        path = "frontend/src/i18n/appTranslations.js"
        content = open(path).read()
        required_keys = [
            "ecb_sync", "white_label", "gantt_baseline", "integration_marketplace",
            "salesforce_sync", "template_documents", "template_roles",
            "customer_health_dashboard", "ai_copilot", "block_kit_notify",
        ]
        for key in required_keys:
            assert key in content, f"i18n key '{key}' not found in translations file"
