"""Tests for Office 365 BI integration endpoints."""
import pytest
from unittest.mock import patch, MagicMock
from tests.conftest import auth


def test_get_o365_config_default(client, admin_token):
    r = client.get("/api/v1/bi/o365/config", headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert "enabled" in data
    assert "tenant_id" in data


def test_save_o365_config(client, admin_token):
    payload = {
        "enabled": True,
        "tenant_id": "test-tenant-123",
        "client_id": "app-client-abc",
        "client_secret": "super-secret",
        "sync_schedule": "0 2 * * *",
        "reports": ["teams_activity", "email_activity"],
    }
    r = client.put("/api/v1/bi/o365/config", json=payload, headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["tenant_id"] == "test-tenant-123"
    # client_secret must NOT be stored/returned
    assert "client_secret" not in data or data.get("client_secret") in (None, "", "***")


def test_trigger_o365_sync_without_config(client, admin_token):
    """Sync without tenant_id configured should fail gracefully."""
    # Reset config first to empty
    client.put("/api/v1/bi/o365/config", json={"enabled": False, "tenant_id": "", "client_id": ""}, headers=auth(admin_token))
    r = client.post("/api/v1/bi/o365/sync", headers=auth(admin_token))
    # Expect 202 with queued/error or 400/422 with clear message
    assert r.status_code in (202, 400, 422)


def test_trigger_o365_sync_with_mock(client, admin_token):
    """Trigger sync with mocked Graph API response."""
    client.put(
        "/api/v1/bi/o365/config",
        json={"enabled": True, "tenant_id": "t1", "client_id": "c1", "client_secret": "s1"},
        headers=auth(admin_token),
    )
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"value": [{"userId": "u1", "reportRefreshDate": "2024-01-01"}]}
    with patch("requests.post") as mock_post, patch("requests.get") as mock_get:
        # Mock token endpoint
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {"access_token": "fake-token", "expires_in": 3600})
        mock_get.return_value = mock_response
        r = client.post("/api/v1/bi/o365/sync", headers=auth(admin_token))
    assert r.status_code in (200, 202)
    data = r.json()["data"]
    assert "status" in data or "queued" in data


def test_get_o365_report_teams(client, admin_token):
    r = client.get("/api/v1/bi/o365/reports/teams_activity", headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert "report" in data or "rows" in data


def test_get_o365_report_unknown(client, admin_token):
    r = client.get("/api/v1/bi/o365/reports/nonexistent_report_xyz", headers=auth(admin_token))
    assert r.status_code in (404, 400)


def test_get_o365_adoption(client, admin_token):
    r = client.get("/api/v1/bi/o365/adoption", headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert isinstance(data, dict)


def test_get_o365_sync_log(client, admin_token):
    r = client.get("/api/v1/bi/o365/sync-log", headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert "log" in data or "entries" in data


def test_o365_auth_required(client):
    r = client.get("/api/v1/bi/o365/config")
    assert r.status_code == 401
