"""Tests de Contratos."""
from tests.conftest import auth


def _create_project(client, token):
    r = client.post("/api/v1/projects", json={
        "name": "Proyecto contratos test", "code": "CTR-TEST",
        "start_date": "2025-01-01", "end_date": "2025-12-31",
    }, headers=auth(token))
    assert r.status_code in (200, 201), f"No se pudo crear proyecto: {r.text}"
    return r.json()["data"]["id"]


def test_list_contracts(client, admin_token, db):
    res = client.get("/api/v1/contracts", headers=auth(admin_token))
    assert res.status_code == 200


def test_create_contract(client, admin_token, db):
    pid = _create_project(client, admin_token)
    res = client.post("/api/v1/contracts",
        headers=auth(admin_token),
        json={"name": "Contrato mantenimiento",
              "project_id": pid,
              "client_name": "Cliente Test",
              "contract_type": "time_material",
              "start_date": "2025-01-01",
              "end_date": "2025-12-31",
              "total_amount": 120000.0})
    assert res.status_code in (200, 201)
    assert "id" in res.json()["data"]


def test_update_contract(client, admin_token, db):
    pid = _create_project(client, admin_token)
    cid = client.post("/api/v1/contracts",
        headers=auth(admin_token),
        json={"name": "Contrato actualizar", "project_id": pid,
              "client_name": "Cliente Test", "contract_type": "fixed_price",
              "start_date": "2025-01-01", "end_date": "2025-06-30", "total_amount": 50000}
    ).json()["data"]["id"]
    res = client.patch(f"/api/v1/contracts/{cid}",
        headers=auth(admin_token),
        json={"total_amount": 60000.0})
    assert res.status_code == 200


def test_delete_contract(client, admin_token, db):
    pid = _create_project(client, admin_token)
    cid = client.post("/api/v1/contracts",
        headers=auth(admin_token),
        json={"name": "Contrato borrar", "project_id": pid,
              "client_name": "Cliente Test", "contract_type": "time_material",
              "start_date": "2025-01-01", "end_date": "2025-12-31", "total_amount": 0}
    ).json()["data"]["id"]
    res = client.delete(f"/api/v1/contracts/{cid}", headers=auth(admin_token))
    assert res.status_code == 200
