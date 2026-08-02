"""tests/test_bi_etl.py — Tests for BI ETL Connector endpoints."""
from tests.conftest import auth


def test_list_connectors(client, admin_token):
    r = client.get("/api/v1/bi/etl/connectors", headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert "connectors" in data
    assert data["count"] > 0
    # Check known connectors are present
    ids = [c["connector_id"] for c in data["connectors"]]
    assert "salesforce" in ids
    assert "jira" in ids


def test_get_connector_detail(client, admin_token):
    r = client.get("/api/v1/bi/etl/connectors/salesforce", headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["connector_id"] == "salesforce"
    assert "enabled" in data
    assert "status" in data
    assert "recent_log" in data


def test_get_connector_not_found(client, admin_token):
    r = client.get("/api/v1/bi/etl/connectors/nonexistent_connector_xyz", headers=auth(admin_token))
    assert r.status_code == 404


def test_trigger_sync(client, admin_token):
    r = client.post("/api/v1/bi/etl/connectors/hubspot/sync", json={}, headers=auth(admin_token))
    # Returns 202 Accepted, even if Celery not available
    assert r.status_code == 202
    data = r.json()["data"]
    assert "connector_id" in data
    assert data["connector_id"] == "hubspot"
    assert "status" in data


def test_trigger_sync_not_found(client, admin_token):
    r = client.post("/api/v1/bi/etl/connectors/nonexistent/sync", json={}, headers=auth(admin_token))
    assert r.status_code == 404


def test_get_sync_log(client, admin_token):
    r = client.get("/api/v1/bi/etl/connectors/jira/log", headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert "entries" in data
    assert "count" in data


def test_get_synced_data(client, admin_token):
    r = client.get("/api/v1/bi/etl/data/stripe", headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["connector_id"] == "stripe"
    assert "data" in data


def test_etl_requires_auth(client):
    r = client.get("/api/v1/bi/etl/connectors")
    assert r.status_code == 401
