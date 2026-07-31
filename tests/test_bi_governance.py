"""tests/test_bi_governance.py — Tests for BI Governance endpoints."""
import pytest
from tests.conftest import auth


def test_get_governance_config(client, admin_token):
    r = client.get("/api/v1/bi/governance/config", headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, dict)


def test_update_governance_config(client, admin_token):
    payload = {
        "require_approval_for_publish": True,
        "data_retention_days": 365,
    }
    r = client.put("/api/v1/bi/governance/config", json=payload, headers=auth(admin_token))
    assert r.status_code == 200


def test_list_access_policies(client, admin_token):
    r = client.get("/api/v1/bi/governance/policies", headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, (list, dict))


def test_create_access_policy(client, admin_token):
    payload = {
        "name": "Finance only",
        "resource_type": "dashboard",
        "resource_id": "dash-finance-1",
        "allowed_roles": ["admin", "pm"],
        "deny_roles": [],
    }
    r = client.post("/api/v1/bi/governance/policies", json=payload, headers=auth(admin_token))
    assert r.status_code in (200, 201)
    data = r.json()["data"]
    assert "id" in data


def test_audit_log(client, admin_token):
    r = client.get("/api/v1/bi/governance/audit-log", headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, (list, dict))


def test_governance_requires_auth(client):
    r = client.get("/api/v1/bi/governance/config")
    assert r.status_code == 401
