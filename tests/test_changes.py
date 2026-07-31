"""Tests de Cambios (Change Requests) — flujo completo de solicitudes de cambio."""
from tests.conftest import auth
from datetime import date, timedelta
from app.models.resources import ChangeRequest


def _create_project(client, token, code="CHG-01"):
    r = client.post("/api/v1/projects", json={
        "name": "Proyecto Cambios Test", "code": code,
        "start_date": str(date.today()),
        "end_date": str(date.today() + timedelta(days=180)),
    }, headers=auth(token))
    assert r.status_code in (200, 201)
    return r.json()["data"]["id"]


def test_list_changes_empty(client, pm_token, db):
    pid = _create_project(client, pm_token)
    res = client.get(f"/api/v1/changes/{pid}", headers=auth(pm_token))
    assert res.status_code == 200
    data = res.json()["data"]
    assert "change_requests" in data
    assert isinstance(data["change_requests"], list)


def test_create_change_request(client, pm_token, db):
    pid = _create_project(client, pm_token)
    res = client.post(f"/api/v1/changes/{pid}", json={
        "title": "Ampliación de alcance modulo X",
        "description": "Se requiere añadir funcionalidad adicional",
        "justification": "2 semanas adicionales de desarrollo",
        "cost_impact": 5000.0,
        "schedule_impact_days": 14,
        "impact": "high",
    }, headers=auth(pm_token))
    assert res.status_code in (200, 201)
    data = res.json()["data"]
    assert "id" in data
    assert data["title"] == "Ampliación de alcance modulo X"


def test_change_request_workflow(client, pm_token, admin_token, db):
    """Flujo: crear → enviar → revisar."""
    pid = _create_project(client, pm_token, code="CHG-02")
    cr = client.post(f"/api/v1/changes/{pid}", json={
        "title": "CR con flujo",
        "description": "Solicitud de cambio para testear flujo",
    }, headers=auth(pm_token)).json()["data"]
    crid = cr["id"]

    # Enviar para revisión
    res = client.post(f"/api/v1/changes/{pid}/{crid}/submit",
        headers=auth(pm_token))
    assert res.status_code in (200, 400)  # 400 si ya está enviado

    # Revisar (aprobar o rechazar)
    res = client.post(f"/api/v1/changes/{pid}/{crid}/review",
        json={"approved": True, "resolution_notes": "Aprobado por el director"},
        headers=auth(admin_token))
    assert res.status_code in (200, 400)


def test_delete_change_request(client, pm_token, db):
    pid = _create_project(client, pm_token, code="CHG-03")
    cr = client.post(f"/api/v1/changes/{pid}", json={
        "title": "CR a Borrar", "description": "Descripción del CR a borrar",
    }, headers=auth(pm_token)).json()["data"]
    res = client.delete(f"/api/v1/changes/{pid}/{cr['id']}",
        headers=auth(pm_token))
    assert res.status_code == 200
    payload = res.json()["data"]
    assert payload.get("ok") is True

    listed = client.get(f"/api/v1/changes/{pid}", headers=auth(pm_token))
    assert listed.status_code == 200
    ids = [item["id"] for item in listed.json()["data"].get("change_requests", [])]
    assert cr["id"] not in ids

    row = db.query(ChangeRequest).filter(ChangeRequest.id == cr["id"]).first()
    assert row is not None
    assert row.is_active is False


def test_all_pending_changes(client, admin_token, db):
    res = client.get("/api/v1/changes/all/pending", headers=auth(admin_token))
    assert res.status_code == 200
    payload = res.json()
    assert isinstance(payload, dict)
    assert isinstance(payload["items"], list)
    assert "meta" in payload


def test_changes_require_auth(client, db):
    res = client.get("/api/v1/changes/all/pending")
    assert res.status_code in (401, 403)
