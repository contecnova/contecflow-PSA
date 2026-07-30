"""tests/test_bi_gdpr.py — Tests for BI GDPR compliance endpoints."""
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
    data = r.json()["data"]
    assert data["user_id"] == "user-123"
    assert data["granted"] is True


def test_get_consent(client, admin_token):
    # first record consent
    client.post("/api/v1/bi/gdpr/consent", json={"user_id": "usr-get", "purpose": "analytics", "granted": True}, headers=auth(admin_token))
    r = client.get("/api/v1/bi/gdpr/consent", params={"user_id": "usr-get"}, headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, (list, dict))


def test_consent_history(client, admin_token):
    """Consent history endpoint returns audit trail after multiple changes."""
    uid = "hist-user-1"
    client.post("/api/v1/bi/gdpr/consent", json={"user_id": uid, "granted": True, "purpose": "analytics", "channel": "web"}, headers=auth(admin_token))
    client.post("/api/v1/bi/gdpr/consent", json={"user_id": uid, "granted": False, "purpose": "analytics", "channel": "api"}, headers=auth(admin_token))
    r = client.get(f"/api/v1/bi/gdpr/consent/{uid}/history", headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert "history" in data
    assert data["count"] >= 2
    actions = [e["action"] for e in data["history"]]
    assert "granted" in actions
    assert "revoked" in actions


def test_create_dsr_erasure(client, admin_token):
    payload = {
        "user_id": "user-erase",
        "request_type": "erasure",
        "notes": "User requested deletion",
    }
    r = client.post("/api/v1/bi/gdpr/dsr", json=payload, headers=auth(admin_token))
    assert r.status_code in (200, 201)
    data = r.json()["data"]
    assert "id" in data
    assert data["request_type"] == "erasure"
    # SLA deadline should be present
    assert data.get("deadline") is not None


def test_create_dsr_portability(client, admin_token):
    r = client.post("/api/v1/bi/gdpr/dsr", json={"user_id": "port-user", "request_type": "portability"}, headers=auth(admin_token))
    assert r.status_code in (200, 201)
    data = r.json()["data"]
    assert data["request_type"] == "portability"
    assert data["status"] == "pending"


def test_create_dsr_restriction(client, admin_token):
    r = client.post("/api/v1/bi/gdpr/dsr", json={"user_id": "rest-user", "request_type": "restriction"}, headers=auth(admin_token))
    assert r.status_code in (200, 201)
    assert r.json()["data"]["request_type"] == "restriction"


def test_get_single_dsr(client, admin_token):
    """GET /bi/gdpr/dsr/{id} returns a single DSR."""
    res = client.post("/api/v1/bi/gdpr/dsr", json={"user_id": "single-u", "request_type": "erasure"}, headers=auth(admin_token))
    dsr_id = res.json()["data"]["id"]
    r = client.get(f"/api/v1/bi/gdpr/dsr/{dsr_id}", headers=auth(admin_token))
    assert r.status_code == 200
    assert r.json()["data"]["id"] == dsr_id


def test_list_dsrs(client, admin_token):
    client.post("/api/v1/bi/gdpr/dsr", json={"user_id": "u1", "request_type": "portability"}, headers=auth(admin_token))
    r = client.get("/api/v1/bi/gdpr/dsr", headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()
    assert "items" in data


def test_list_dsrs_status_filter(client, admin_token):
    """Filter by status=pending returns only pending DSRs."""
    client.post("/api/v1/bi/gdpr/dsr", json={"user_id": "filt-u", "request_type": "erasure"}, headers=auth(admin_token))
    r = client.get("/api/v1/bi/gdpr/dsr", params={"status": "pending"}, headers=auth(admin_token))
    assert r.status_code == 200
    items = r.json()["items"]
    assert all(i["status"] == "pending" for i in items)


def test_resolve_dsr(client, admin_token):
    res = client.post("/api/v1/bi/gdpr/dsr", json={"user_id": "u2", "request_type": "erasure"}, headers=auth(admin_token))
    dsr_id = res.json()["data"]["id"]
    r = client.patch(f"/api/v1/bi/gdpr/dsr/{dsr_id}", json={"status": "completed"}, headers=auth(admin_token))
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "completed"


def test_resolve_dsr_compat_completion_requires_admin(client, admin_token, dev_token):
    """A non-admin must not be able to trigger the erasure pipeline via the
    compat PATCH by setting status=completed."""
    res = client.post(
        "/api/v1/bi/gdpr/dsr",
        json={"user_id": "u-gate", "request_type": "erasure"},
        headers=auth(admin_token),
    )
    dsr_id = res.json()["data"]["id"]
    r = client.patch(
        f"/api/v1/bi/gdpr/dsr/{dsr_id}",
        json={"status": "completed"},
        headers=auth(dev_token),
    )
    assert r.status_code == 403


def test_gdpr_stats(client, admin_token):
    """Stats endpoint returns summary counts."""
    client.post("/api/v1/bi/gdpr/dsr", json={"user_id": "stats-u", "request_type": "erasure"}, headers=auth(admin_token))
    r = client.get("/api/v1/bi/gdpr/stats", headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert "pending" in data
    assert "completed" in data
    assert "overdue" in data
    assert "by_type" in data
    assert "total_consents" in data


def test_portability_export_endpoint(client, admin_token):
    """Portability export returns data package and resolves DSR."""
    res = client.post("/api/v1/bi/gdpr/dsr", json={"user_id": "port-exp-u", "request_type": "portability"}, headers=auth(admin_token))
    dsr_id = res.json()["data"]["id"]
    r = client.post(f"/api/v1/bi/gdpr/dsr/{dsr_id}/portability-export", headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["ok"] is True
    assert "export" in data
    assert data["export"]["export_type"] == "portability"
    assert "data" in data["export"]
    # DSR should be auto-resolved
    r2 = client.get(f"/api/v1/bi/gdpr/dsr/{dsr_id}", headers=auth(admin_token))
    assert r2.json()["data"]["status"] == "completed"


def test_portability_wrong_type_rejected(client, admin_token):
    """Portability export on non-portability DSR returns 422."""
    res = client.post("/api/v1/bi/gdpr/dsr", json={"user_id": "wrong-type", "request_type": "erasure"}, headers=auth(admin_token))
    dsr_id = res.json()["data"]["id"]
    r = client.post(f"/api/v1/bi/gdpr/dsr/{dsr_id}/portability-export", headers=auth(admin_token))
    assert r.status_code == 422


def test_field_masks(client, admin_token):
    # Set a field mask
    payload = {"entity": "user", "field": "email", "mask_type": "hash"}
    r = client.post("/api/v1/bi/gdpr/field-masks", json=payload, headers=auth(admin_token))
    assert r.status_code in (200, 201)
    # List field masks
    r2 = client.get("/api/v1/bi/gdpr/field-masks", headers=auth(admin_token))
    assert r2.status_code == 200
    items = r2.json().get("items", [])
    assert any(m["field"] == "email" for m in items)


def test_field_mask_all_types(client, admin_token):
    """All mask types are accepted."""
    for mt in ["hash", "redact", "suppress", "pseudonymize"]:
        r = client.post("/api/v1/bi/gdpr/field-masks", json={"entity": "ticket", "field": f"f_{mt}", "mask_type": mt}, headers=auth(admin_token))
        assert r.status_code in (200, 201), f"mask_type {mt} failed"


def test_gdpr_requires_auth(client):
    r = client.get("/api/v1/bi/gdpr/consent")
    assert r.status_code == 401
