"""Tests for new stub endpoints: ai_suggestions, resource_demand, health_composite, ui, templates, ai."""


def test_ai_suggestions_gantt(client, admin_token, db):
    headers = {"Authorization": f"Bearer {admin_token}"}
    res = client.get("/api/v1/ai/suggestions/gantt/proj-1", headers=headers)
    assert res.status_code in (200, 404)
    if res.status_code == 200:
        data = res.json()
        assert isinstance(data, list)


def test_ai_suggestions_timesheets(client, admin_token, db):
    headers = {"Authorization": f"Bearer {admin_token}"}
    # Query own anomalies (admin id) — querying a non-existent user_id 404s by design (tenant guard)
    res = client.get("/api/v1/ai/suggestions/timesheets/admin-test-id", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "anomalies" in data


def test_resource_demand_pipeline(client, admin_token, db):
    headers = {"Authorization": f"Bearer {admin_token}"}
    res = client.get("/api/v1/resource-demand/pipeline", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "demand" in data
    assert "projects" in data


def test_health_composite_client(client, admin_token, db):
    headers = {"Authorization": f"Bearer {admin_token}"}
    res = client.get("/api/v1/clients/client-1/health-composite", headers=headers)
    assert res.status_code in (200, 404)
    if res.status_code == 200:
        data = res.json()
        assert "score" in data
        assert "category" in data


def test_health_composite_customers(client, admin_token, db):
    headers = {"Authorization": f"Bearer {admin_token}"}
    res = client.get("/api/v1/customers/c-1/health-composite", headers=headers)
    assert res.status_code in (200, 404)
    if res.status_code == 200:
        assert res.json()["score"] >= 0


def test_ui_accessibility(client, admin_token, db):
    headers = {"Authorization": f"Bearer {admin_token}"}
    res = client.get("/api/v1/ui/accessibility", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "elements" in data
    assert len(data["elements"]) > 0
    assert all("aria-label" in e for e in data["elements"])


def test_ui_keyboard_nav(client, admin_token, db):
    headers = {"Authorization": f"Bearer {admin_token}"}
    res = client.get("/api/v1/ui/keyboard-nav", headers=headers)
    assert res.status_code == 200
    assert res.json()["tabindex"] == 0


def test_ui_labels_default(client, admin_token, db):
    headers = {"Authorization": f"Bearer {admin_token}"}
    res = client.get("/api/v1/ui/labels", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "projects" in data
    assert "dashboard" in data


def test_ui_labels_french(client, admin_token, db):
    headers = {"Authorization": f"Bearer {admin_token}"}
    res = client.get("/api/v1/ui/labels?lang=fr", headers=headers)
    assert res.status_code == 200
    assert res.json()["projects"] == "Projet"


def _create_template(client, headers) -> str:
    """Create a project template via the canonical config endpoint and return its id."""
    res = client.post(
        "/api/v1/advanced-config/templates",
        json={"name": "New Endpoints Template", "project_type": "fixed_price", "estimated_weeks": 8},
        headers=headers,
    )
    assert res.status_code in (200, 201), res.text
    return res.json()["id"]


def test_templates_full(client, admin_token, db):
    headers = {"Authorization": f"Bearer {admin_token}"}
    tmpl_id = _create_template(client, headers)
    res = client.get(f"/api/v1/templates/{tmpl_id}/full", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == tmpl_id
    assert "phases" in data


def test_templates_add_document(client, admin_token, db):
    headers = {"Authorization": f"Bearer {admin_token}"}
    tmpl_id = _create_template(client, headers)
    res = client.post(
        f"/api/v1/templates/{tmpl_id}/documents",
        json={"name": "SOW", "is_required": True},
        headers=headers,
    )
    assert res.status_code in (201, 200)
    data = res.json()
    assert data.get("created", True) is True


def test_templates_add_role(client, admin_token, db):
    headers = {"Authorization": f"Bearer {admin_token}"}
    tmpl_id = _create_template(client, headers)
    res = client.post(
        f"/api/v1/templates/{tmpl_id}/roles",
        json={"role_name": "Developer", "is_mandatory": True},
        headers=headers,
    )
    assert res.status_code in (201, 200)
    data = res.json()
    assert data.get("created", True) is True


def test_templates_export_project(client, admin_token, db):
    headers = {"Authorization": f"Bearer {admin_token}"}
    # export requires a real project to derive the template from
    from app.models.project import Project, ProjectStatus, ProjectType

    proj = Project(
        id="export-tpl-project",
        organization_id=1,
        code="PRJ-EXP",
        name="Export Source Project",
        project_type=ProjectType.consulting,
        status=ProjectStatus.active,
        created_by="admin-test-id",
    )
    db.add(proj)
    db.commit()
    res = client.post(
        "/api/v1/templates/export",
        json={"project_id": "export-tpl-project", "name": "My Template"},
        headers=headers,
    )
    assert res.status_code in (201, 200), res.text
    assert "template_id" in res.json()


def test_endpoints_require_auth(client, db):
    """All new endpoints should reject unauthenticated requests."""
    endpoints = [
        ("GET", "/api/v1/ai/suggestions/gantt/proj-1"),
        ("GET", "/api/v1/ai/suggestions/timesheets/usr-1"),
        ("GET", "/api/v1/resource-demand/pipeline"),
        ("GET", "/api/v1/customers/c-1/health-composite"),
        ("GET", "/api/v1/ui/accessibility"),
    ]
    for method, url in endpoints:
        res = getattr(client, method.lower())(url)
        assert res.status_code == 401, f"{method} {url} should require auth, got {res.status_code}"
