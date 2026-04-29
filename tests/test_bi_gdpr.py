"""tests/test_bi_gdpr.py — Tests for BI GDPR compliance endpoints."""
import pytest
from tests.conftest import auth


def test_record_consent(client, admin_token):
    payload = {
        "user_id": "user-123",
        "purpose": "analytics",
        "granted": True,
        "channel": "web",
    }
    r = client.post("/api/v1/bi/gdpr/consent", json=payload, headers=auth(admin_token))
    assert r.status_code in (200, 201)
    data = r.json()
    assert data["user_id"] == "user-123"
    assert data["granted"] is True


def test_get_consent(client, admin_token):
    # first record consent
    client.post("/api/v1/bi/gdpr/consent", json={"user_id": "usr-get", "purpose": "analytics", "granted": True}, headers=auth(admin_token))
    r = client.get("/api/v1/bi/gdpr/consent", params={"user_id": "usr-get"}, headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, (list, dict))


def test_create_dsr_erasure(client, admin_token):
    payload = {
        "user_id": "user-erase",
        "request_type": "erasure",
        "notes": "User requested deletion",
    }
    r = client.post("/api/v1/bi/gdpr/dsr", json=payload, headers=auth(admin_token))
    assert r.status_code in (200, 201)
    data = r.json()
    assert "id" in data
    assert data["request_type"] == "erasure"


def test_list_dsrs(client, admin_token):
    client.post("/api/v1/bi/gdpr/dsr", json={"user_id": "u1", "request_type": "portability"}, headers=auth(admin_token))
    r = client.get("/api/v1/bi/gdpr/dsr", headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()
    assert "items" in data


def test_resolve_dsr(client, admin_token):
    res = client.post("/api/v1/bi/gdpr/dsr", json={"user_id": "u2", "request_type": "erasure"}, headers=auth(admin_token))
    dsr_id = res.json()["id"]
    r = client.patch(f"/api/v1/bi/gdpr/dsr/{dsr_id}", json={"status": "completed"}, headers=auth(admin_token))
    assert r.status_code == 200
    assert r.json()["status"] == "completed"


def test_field_masks(client, admin_token):
    # Set a field mask
    payload = {"entity": "user", "field": "email", "mask_type": "hash"}
    r = client.post("/api/v1/bi/gdpr/field-masks", json=payload, headers=auth(admin_token))
    assert r.status_code in (200, 201)
    # List field masks
    r2 = client.get("/api/v1/bi/gdpr/field-masks", headers=auth(admin_token))
    assert r2.status_code == 200


def test_gdpr_requires_auth(client):
    r = client.get("/api/v1/bi/gdpr/consent")
    assert r.status_code == 401
