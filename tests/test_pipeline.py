"""Tests de Pipeline CRM — oportunidades, etapas, forecast."""
from tests.conftest import auth


def test_list_pipeline_empty(client, admin_token, db):
    res = client.get("/api/v1/pipeline", headers=auth(admin_token))
    assert res.status_code == 200
    data = res.json()
    items = data if isinstance(data, list) else data.get("items", [])
    assert isinstance(items, list)


def test_create_opportunity(client, admin_token, db):
    res = client.post("/api/v1/pipeline",
        headers=auth(admin_token),
        json={"name": "Proyecto cliente ABC", "client_name": "Cliente ABC",
              "stage": "lead", "expected_revenue": 50000.0, "probability": 30})
    assert res.status_code in (200, 201)
    data = res.json()["data"]
    assert "id" in data


def test_update_opportunity_stage(client, admin_token, db):
    opp_id = client.post("/api/v1/pipeline",
        headers=auth(admin_token),
        json={"name": "Oportunidad cambio etapa", "client_name": "Cliente X",
              "stage": "lead", "expected_revenue": 25000}
    ).json()["data"]["id"]
    res = client.patch(f"/api/v1/pipeline/{opp_id}",
        headers=auth(admin_token),
        json={"stage": "proposal", "probability": 60})
    assert res.status_code == 200


def test_delete_opportunity(client, admin_token, db):
    opp_id = client.post("/api/v1/pipeline",
        headers=auth(admin_token),
        json={"name": "Oportunidad borrar", "client_name": "Cliente Y",
              "stage": "lost", "expected_revenue": 0}
    ).json()["data"]["id"]
    res = client.delete(f"/api/v1/pipeline/{opp_id}", headers=auth(admin_token))
    assert res.status_code == 200


def test_employee_cannot_delete_opportunity(client, dev_token, db):
    res = client.delete("/api/v1/pipeline/nonexistent-id", headers=auth(dev_token))
    assert res.status_code in (403, 401, 404)
