"""Tests for new stub endpoints: ai_suggestions, resource_demand, health_composite, ui, templates, ai."""


def test_ai_suggestions_gantt(client, admin_token, db):
    headers = {"Authorization": f"Bearer {admin_token}"}
    res = client.get("/api/v1/ai/suggestions/gantt/proj-1", headers=headers)
    assert res.status_code in (200, 404)
    if res.status_code == 200:
        data = res.json()["data"]
        assert isinstance(data["suggestions"], list)


def test_ai_suggestions_timesheets(client, admin_token, db):
    headers = {"Authorization": f"Bearer {admin_token}"}
    # Query own anomalies (admin id) — querying a non-existent user_id 404s by design (tenant guard)
    res = client.get("/api/v1/ai/suggestions/timesheets/admin-test-id", headers=headers)
    assert res.status_code == 200
    data = res.json()["data"]
    assert "anomalies" in data


def test_resource_demand_pipeline(client, admin_token, db):
    headers = {"Authorization": f"Bearer {admin_token}"}
    res = client.get("/api/v1/resource-demand/pipeline", headers=headers)
    assert res.status_code == 200
    data = res.json()["data"]
    assert "demand" in data
    assert "projects" in data


def test_health_composite_client(client, admin_token, db):
    headers = {"Authorization": f"Bearer {admin_token}"}
    res = client.get("/api/v1/clients/client-1/health-composite", headers=headers)
    assert res.status_code in (200, 404)
    if res.status_code == 200:
        data = res.json()["data"]
        assert "score" in data
        assert "category" in data


def test_health_composite_customers(client, admin_token, db):
    headers = {"Authorization": f"Bearer {admin_token}"}
    res = client.get("/api/v1/customers/c-1/health-composite", headers=headers)
    assert res.status_code in (200, 404)
    if res.status_code == 200:
        assert res.json()["data"]["score"] >= 0


def test_ui_de_relleno_retirado(client, admin_token, db):
    """18-11-2026: `/ui/*` era un relleno con textos fijos que no usaba nadie."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    for ruta in ("/api/v1/ui/accessibility", "/api/v1/ui/keyboard-nav", "/api/v1/ui/labels"):
        assert client.get(ruta, headers=headers).status_code == 404


def _create_template(client, headers) -> str:
    """Create a project template via the canonical config endpoint and return its id."""
    res = client.post(
        "/api/v1/advanced-config/templates",
        json={"name": "New Endpoints Template", "project_type": "fixed_price", "estimated_weeks": 8},
        headers=headers,
    )
    assert res.status_code in (200, 201), res.text
    return res.json()["data"]["id"]


def test_templates_full(client, admin_token, db):
    headers = {"Authorization": f"Bearer {admin_token}"}
    tmpl_id = _create_template(client, headers)
    res = client.get(f"/api/v1/templates/{tmpl_id}/full", headers=headers)
    assert res.status_code == 200
    data = res.json()["data"]
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
    data = res.json()["data"]
    assert data["created"] is True


def test_templates_add_role(client, admin_token, db):
    headers = {"Authorization": f"Bearer {admin_token}"}
    tmpl_id = _create_template(client, headers)
    res = client.post(
        f"/api/v1/templates/{tmpl_id}/roles",
        json={"role_name": "Developer", "is_mandatory": True},
        headers=headers,
    )
    assert res.status_code in (201, 200)
    data = res.json()["data"]
    assert data["created"] is True


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
    assert "template_id" in res.json()["data"]


def test_endpoints_require_auth(client, db):
    """All new endpoints should reject unauthenticated requests."""
    endpoints = [
        ("GET", "/api/v1/ai/suggestions/gantt/proj-1"),
        ("GET", "/api/v1/ai/suggestions/timesheets/usr-1"),
        ("GET", "/api/v1/resource-demand/pipeline"),
        ("GET", "/api/v1/customers/c-1/health-composite"),
    ]
    for method, url in endpoints:
        res = getattr(client, method.lower())(url)
        assert res.status_code == 401, f"{method} {url} should require auth, got {res.status_code}"
