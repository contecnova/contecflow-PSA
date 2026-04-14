"""Tests de Clientes (CRM) — CRUD, contactos, 360."""
from tests.conftest import auth


def _create_client(client, token, name="Cliente Test SA"):
    res = client.post("/api/v1/clients", json={
        "name": name,
        "industry": "technology",
        "contact_name": "Ana García",
        "contact_email": "ana@cliente.com",
        "country": "ES",
    }, headers=auth(token))
    assert res.status_code in (200, 201), f"No se pudo crear cliente: {res.text}"
    return res.json()["id"]


def test_list_clients_empty(client, admin_token, db):
    res = client.get("/api/v1/clients", headers=auth(admin_token))
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, (list, dict))


def test_create_client(client, admin_token, db):
    res = client.post("/api/v1/clients", json={
        "name": "Empresa XYZ SL",
        "industry": "finance",
        "contact_name": "Carlos López",
        "contact_email": "carlos@xyz.com",
    }, headers=auth(admin_token))
    assert res.status_code in (200, 201)
    data = res.json()
    assert "id" in data
    assert data["name"] == "Empresa XYZ SL"


def test_get_client_detail(client, admin_token, db):
    cid = _create_client(client, admin_token)
    res = client.get(f"/api/v1/clients/{cid}", headers=auth(admin_token))
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == cid


def test_update_client(client, admin_token, db):
    cid = _create_client(client, admin_token)
    res = client.patch(f"/api/v1/clients/{cid}",
        json={"industry": "healthcare", "contact_phone": "+34 600 000 001"},
        headers=auth(admin_token))
    assert res.status_code == 200


def test_delete_client(client, admin_token, db):
    cid = _create_client(client, admin_token, name="Cliente a Borrar")
    res = client.delete(f"/api/v1/clients/{cid}", headers=auth(admin_token))
    assert res.status_code in (200, 204)


def test_client_not_found(client, admin_token, db):
    res = client.get("/api/v1/clients/nonexistent-cid", headers=auth(admin_token))
    assert res.status_code == 404


def test_add_contact_to_client(client, admin_token, db):
    cid = _create_client(client, admin_token)
    res = client.post(f"/api/v1/clients/{cid}/contacts", json={
        "full_name": "María Fernández",
        "email": "maria@cliente.com",
        "role": "technical",
    }, headers=auth(admin_token))
    assert res.status_code in (200, 201)
    data = res.json()
    assert "id" in data


def test_list_contacts(client, admin_token, db):
    cid = _create_client(client, admin_token)
    res = client.get(f"/api/v1/clients/{cid}/contacts", headers=auth(admin_token))
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_client_360_view(client, admin_token, db):
    cid = _create_client(client, admin_token)
    res = client.get(f"/api/v1/clients/{cid}/360", headers=auth(admin_token))
    assert res.status_code == 200


def test_employee_cannot_create_client(client, dev_token, db):
    res = client.post("/api/v1/clients", json={"name": "Intento No Autorizado"},
        headers=auth(dev_token))
    assert res.status_code in (401, 403)


def test_client_requires_auth(client, db):
    res = client.get("/api/v1/clients")
    assert res.status_code in (401, 403)
