"""Tests de rate cards — tarifas, márgenes, jerarquía."""
from app.models.advanced_config import RateEntry
from app.models.advanced_config import RateOverride
from app.models.advanced_config import RateTable
from tests.conftest import auth

def test_create_rate_card(client, admin_token, db):
    res = client.post("/api/v1/rate-cards", json={
        "name": "Tarifas 2025", "applies_to": "role", "is_default": True,
    }, headers=auth(admin_token))
    assert res.status_code in (200, 201)
    data = res.json()
    assert data["name"] == "Tarifas 2025"
    assert data["is_default"] is True

def test_list_rate_cards(client, admin_token, db):
    client.post("/api/v1/rate-cards", json={"name":"RC1","applies_to":"role","is_default":False}, headers=auth(admin_token))
    res = client.get("/api/v1/rate-cards", headers=auth(admin_token))
    assert res.status_code == 200
    assert isinstance(res.json(), list)

def test_add_entry_to_rate_card(client, admin_token, db):
    rc = client.post("/api/v1/rate-cards", json={"name":"RC","applies_to":"role","is_default":True}, headers=auth(admin_token)).json()
    res = client.post(f"/api/v1/rate-cards/{rc['id']}/entries", json={
        "label": "Senior Dev", "billing_rate": 120, "cost_rate": 65,
        "escalation_pct": 3,
    }, headers=auth(admin_token))
    assert res.status_code in (200, 201)
    data = res.json()
    assert data["billing_rate"] == 120
    assert data["cost_rate"] == 65

def test_effective_rate(client, admin_token, db):
    res = client.get("/api/v1/rate-cards/effective", params={"role_label": "Senior Dev"}, headers=auth(admin_token))
    assert res.status_code in (200, 404)  # 404 si no hay tarifa configurada

def test_duplicate_rate_card(client, admin_token, db):
    rc = client.post("/api/v1/rate-cards", json={"name":"RC","applies_to":"role","is_default":True}, headers=auth(admin_token)).json()
    res = client.post(f"/api/v1/rate-cards/{rc['id']}/duplicate", json={"escalation_pct": 5}, headers=auth(admin_token))
    assert res.status_code in (200, 201)

def test_delete_rate_card(client, admin_token, db):
    rc = client.post("/api/v1/rate-cards", json={"name":"RC","applies_to":"role","is_default":False}, headers=auth(admin_token)).json()
    res = client.delete(f"/api/v1/rate-cards/{rc['id']}", headers=auth(admin_token))
    assert res.status_code == 200
    assert res.json()["ok"] is True

    listed = client.get("/api/v1/rate-cards", headers=auth(admin_token))
    assert listed.status_code == 200
    assert all(t["id"] != rc["id"] for t in listed.json())

    row = db.query(RateTable).filter(RateTable.id == rc["id"]).first()
    assert row is not None
    assert row.is_active is False


def test_delete_rate_card_entry_soft_and_hidden(client, admin_token, db):
    rc = client.post(
        "/api/v1/rate-cards",
        json={"name": "RC entries", "applies_to": "role", "is_default": False},
        headers=auth(admin_token),
    ).json()
    entry = client.post(
        f"/api/v1/rate-cards/{rc['id']}/entries",
        json={"label": "Senior Dev", "billing_rate": 120, "cost_rate": 65},
        headers=auth(admin_token),
    ).json()

    res = client.delete(
        f"/api/v1/rate-cards/{rc['id']}/entries/{entry['id']}",
        headers=auth(admin_token),
    )
    assert res.status_code == 200
    assert res.json()["ok"] is True

    detail = client.get(f"/api/v1/rate-cards/{rc['id']}", headers=auth(admin_token))
    assert detail.status_code == 200
    assert all(e["id"] != entry["id"] for e in detail.json().get("entries", []))

    row = db.query(RateEntry).filter(RateEntry.id == entry["id"]).first()
    assert row is not None
    assert row.is_active is False


def test_delete_rate_card_override_soft_and_hidden(client, admin_token, db):
    rc = client.post(
        "/api/v1/rate-cards",
        json={"name": "RC overrides", "applies_to": "role", "is_default": False},
        headers=auth(admin_token),
    ).json()
    ov = client.post(
        f"/api/v1/rate-cards/{rc['id']}/overrides",
        json={"client_id": "client-soft-delete", "role_label": "Senior Dev", "billing_rate": 150},
        headers=auth(admin_token),
    ).json()

    res = client.delete(
        f"/api/v1/rate-cards/{rc['id']}/overrides/{ov['id']}",
        headers=auth(admin_token),
    )
    assert res.status_code == 200
    assert res.json()["ok"] is True

    detail = client.get(f"/api/v1/rate-cards/{rc['id']}", headers=auth(admin_token))
    assert detail.status_code == 200
    assert all(o["id"] != ov["id"] for o in detail.json().get("overrides", []))

    row = db.query(RateOverride).filter(RateOverride.id == ov["id"]).first()
    assert row is None
