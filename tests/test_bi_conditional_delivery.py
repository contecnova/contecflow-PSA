"""tests/test_bi_conditional_delivery.py — Tests for BI Conditional Delivery endpoints."""
import pytest
from tests.conftest import auth


def test_create_rule(client, admin_token):
    payload = {
        "name": "Revenue alert",
        "report_id": "rpt-1",
        "condition_type": "diff_threshold",
        "threshold_pct": 10.0,
        "recipients": ["admin@contecflow.com"],
        "schedule": "0 9 * * 1",  # every Monday 9am
    }
    r = client.post("/api/v1/bi/delivery/rules", json=payload, headers=auth(admin_token))
    assert r.status_code in (200, 201)
    data = r.json()["data"]
    assert "id" in data
    assert data["name"] == "Revenue alert"


def test_list_rules(client, admin_token):
    client.post("/api/v1/bi/delivery/rules", json={"name": "r1", "report_id": "rpt-2", "condition_type": "always"}, headers=auth(admin_token))
    r = client.get("/api/v1/bi/delivery/rules", headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert "items" in data


def test_update_rule(client, admin_token):
    res = client.post("/api/v1/bi/delivery/rules", json={"name": "r2", "report_id": "rpt-3", "condition_type": "always"}, headers=auth(admin_token))
    rule_id = res.json()["data"]["id"]
    r = client.patch(f"/api/v1/bi/delivery/rules/{rule_id}", json={"enabled": False}, headers=auth(admin_token))
    assert r.status_code == 200
    assert r.json()["data"]["enabled"] is False


def test_evaluate_rule(client, admin_token):
    res = client.post("/api/v1/bi/delivery/rules", json={"name": "eval-rule", "report_id": "rpt-4", "condition_type": "diff_threshold", "threshold_pct": 5.0}, headers=auth(admin_token))
    rule_id = res.json()["data"]["id"]
    r = client.post(f"/api/v1/bi/delivery/rules/{rule_id}/evaluate", headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert "should_deliver" in data


def test_delete_rule(client, admin_token):
    res = client.post(
        "/api/v1/bi/delivery/rules",
        json={"name": "delete-rule", "report_id": "rpt-5", "condition_type": "always"},
        headers=auth(admin_token),
    )
    rule_id = res.json()["data"]["id"]

    deleted = client.delete(f"/api/v1/bi/delivery/rules/{rule_id}", headers=auth(admin_token))
    assert deleted.status_code in (200, 204)

    listed = client.get("/api/v1/bi/delivery/rules", headers=auth(admin_token))
    assert listed.status_code == 200
    assert all(r["id"] != rule_id for r in listed.json()["data"].get("items", []))


def test_conditional_delivery_requires_auth(client):
    r = client.get("/api/v1/bi/delivery/rules")
    assert r.status_code == 401
