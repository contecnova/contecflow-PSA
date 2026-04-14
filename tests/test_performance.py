"""Tests de Performance Reviews — ciclos, evaluaciones, submit."""
from tests.conftest import auth


def test_list_cycles_empty(client, admin_token, db):
    res = client.get("/api/v1/performance/cycles", headers=auth(admin_token))
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_create_cycle(client, admin_token, db):
    res = client.post("/api/v1/performance/cycles",
        headers=auth(admin_token),
        json={"name": "Evaluación Q2 2025", "start_date": "2025-04-01", "end_date": "2025-06-30"})
    assert res.status_code == 201
    data = res.json()
    assert "id" in data
    assert data["name"] == "Evaluación Q2 2025"


def test_create_cycle_requires_name(client, admin_token, db):
    res = client.post("/api/v1/performance/cycles",
        headers=auth(admin_token),
        json={"start_date": "2025-01-01"})
    assert res.status_code == 422


def test_employee_cannot_create_cycle(client, dev_token, db):
    res = client.post("/api/v1/performance/cycles",
        headers=auth(dev_token),
        json={"name": "Ciclo no autorizado"})
    assert res.status_code in (403, 401)


def test_activate_cycle(client, admin_token, db):
    cycle_id = client.post("/api/v1/performance/cycles",
        headers=auth(admin_token),
        json={"name": "Ciclo activar"}
    ).json()["id"]
    res = client.post(f"/api/v1/performance/cycles/{cycle_id}/activate",
        headers=auth(admin_token))
    assert res.status_code == 200
    assert res.json()["status"] == "active"


def test_close_cycle(client, admin_token, db):
    cycle_id = client.post("/api/v1/performance/cycles",
        headers=auth(admin_token),
        json={"name": "Ciclo cerrar"}
    ).json()["id"]
    client.post(f"/api/v1/performance/cycles/{cycle_id}/activate", headers=auth(admin_token))
    res = client.post(f"/api/v1/performance/cycles/{cycle_id}/close",
        headers=auth(admin_token))
    assert res.status_code == 200
    assert res.json()["status"] == "closed"


def test_my_reviews_empty(client, dev_token, db):
    res = client.get("/api/v1/performance/my-reviews", headers=auth(dev_token))
    assert res.status_code == 200
    assert isinstance(res.json(), list)
