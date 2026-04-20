from sqlalchemy import text
"""Tests for new stub endpoints: ai_suggestions, resource_demand, health_composite, ui, templates, ai."""


def test_ai_suggestions_gantt(client, admin_token, db):
    headers = {"Authorization": f"Bearer {admin_token}"}
    res = client.get("/api/v1/ai/suggestions/gantt/proj-1", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)


def test_ai_suggestions_timesheets(client, admin_token, db):
    headers = {"Authorization": f"Bearer {admin_token}"}
    res = client.get("/api/v1/ai/suggestions/timesheets/usr-1", headers=headers)
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
    assert res.status_code == 200
    data = res.json()
    assert "score" in data
    assert "category" in data


def test_health_composite_customers(client, admin_token, db):
    headers = {"Authorization": f"Bearer {admin_token}"}
    res = client.get("/api/v1/customers/c-1/health-composite", headers=headers)
    assert res.status_code == 200
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


def test_templates_full(client, admin_token, db):
    headers = {"Authorization": f"Bearer {admin_token}"}
    res = client.get("/api/v1/templates/tpl-1/full", headers=headers)
    assert res.status_code == 200
    assert "template" in res.json()


def test_templates_add_document(client, admin_token, db):
    headers = {"Authorization": f"Bearer {admin_token}"}
    # Limpieza previa para evitar duplicados
    db.execute(text('DELETE FROM template_document'))
    db.commit()
    res = client.post("/api/v1/templates/tpl-1/documents", headers=headers)
    assert res.status_code in (201, 200)
    data = res.json()
    assert data.get("ok", True) is True


def test_templates_add_role(client, admin_token, db):
    headers = {"Authorization": f"Bearer {admin_token}"}
    db.execute(text('DELETE FROM template_role'))
    db.commit()
    res = client.post("/api/v1/templates/tpl-1/roles", headers=headers)
    assert res.status_code in (201, 200)
    data = res.json()
    assert data.get("ok", True) is True


def test_templates_export_project(client, admin_token, db):
    headers = {"Authorization": f"Bearer {admin_token}"}
    db.execute(text('DELETE FROM template_export'))
    db.commit()
    res = client.post("/api/v1/templates/export", headers=headers)
    assert res.status_code in (201, 200)
    assert "template_id" in res.json()


def test_ai_status(client, admin_token, db):
    headers = {"Authorization": f"Bearer {admin_token}"}
    res = client.get("/api/v1/ai/status", headers=headers)
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_endpoints_require_auth(client, db):
    """All new endpoints should reject unauthenticated requests."""
    endpoints = [
        ("GET", "/api/v1/ai/suggestions/gantt/proj-1"),
        ("GET", "/api/v1/ai/suggestions/timesheets/usr-1"),
        ("GET", "/api/v1/resource-demand/pipeline"),
        ("GET", "/api/v1/customers/c-1/health-composite"),
        ("GET", "/api/v1/ui/accessibility"),
        ("GET", "/api/v1/ai/status"),
    ]
    for method, url in endpoints:
        res = getattr(client, method.lower())(url)
        assert res.status_code == 401, f"{method} {url} should require auth, got {res.status_code}"
