"""Tests de Gestión de Riesgos — CRUD, portfolio de riesgos."""
from tests.conftest import auth


def _create_project(client, token, code="RSK-01"):
    r = client.post("/api/v1/projects", json={
        "name": "Proyecto Riesgos Test", "code": code,
        "start_date": "2025-01-01", "end_date": "2025-12-31",
    }, headers=auth(token))
    assert r.status_code in (200, 201)
    return r.json()["id"]


def test_list_project_risks_empty(client, admin_token, db):
    pid = _create_project(client, admin_token)
    res = client.get(f"/api/v1/risks/{pid}", headers=auth(admin_token))
    assert res.status_code == 200
    data = res.json()
    assert "risks" in data
    assert isinstance(data["risks"], list)


def test_create_risk(client, admin_token, db):
    pid = _create_project(client, admin_token)
    res = client.post(f"/api/v1/risks/{pid}", json={
        "title": "Riesgo de retraso tecnológico",
        "description": "Posible retraso por cambio de tecnología",
        "probability": "medium",
        "impact": "major",
        "mitigation": "Plan alternativo con tecnología probada",
    }, headers=auth(admin_token))
    assert res.status_code in (200, 201)
    data = res.json()
    assert "id" in data
    assert data["probability"] == "medium"
    assert data["impact"] == "major"


def test_risk_score_computed(client, admin_token, db):
    """El sistema calcula automáticamente el score del riesgo."""
    pid = _create_project(client, admin_token, code="RSK-02")
    res = client.post(f"/api/v1/risks/{pid}", json={
        "title": "Riesgo crítico",
        "probability": "high",
        "impact": "critical",
        "mitigation": "Mitigación urgente",
    }, headers=auth(admin_token))
    assert res.status_code in (200, 201)
    data = res.json()
    assert "risk_score" in data
    assert data["risk_score"] > 0


def test_update_risk(client, admin_token, db):
    pid = _create_project(client, admin_token, code="RSK-03")
    risk = client.post(f"/api/v1/risks/{pid}", json={
        "title": "Riesgo a actualizar",
        "probability": "low",
        "impact": "moderate",
    }, headers=auth(admin_token)).json()
    res = client.patch(f"/api/v1/risks/{pid}/{risk['id']}",
        json={"probability": "high", "status": "monitoring"},
        headers=auth(admin_token))
    assert res.status_code == 200


def test_delete_risk(client, admin_token, db):
    pid = _create_project(client, admin_token, code="RSK-04")
    risk = client.post(f"/api/v1/risks/{pid}", json={
        "title": "Riesgo a borrar",
        "probability": "low",
        "impact": "minor",
    }, headers=auth(admin_token)).json()
    res = client.delete(f"/api/v1/risks/{pid}/{risk['id']}", headers=auth(admin_token))
    assert res.status_code in (200, 204)


def test_portfolio_risks(client, admin_token, db):
    """Vista de riesgos de todos los proyectos."""
    res = client.get("/api/v1/risks/all/portfolio", headers=auth(admin_token))
    assert res.status_code == 200


def test_risk_requires_auth(client, db):
    res = client.get("/api/v1/risks/some-project-id")
    assert res.status_code in (401, 403)
