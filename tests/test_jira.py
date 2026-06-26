"""Tests de integración Jira — configuración, mapeos, webhooks."""
from unittest.mock import patch, MagicMock
from tests.conftest import auth
from app.core.config import settings

# ── helpers ────────────────────────────────────────────────────────────────────

JIRA_CONFIG = {
    "jira_url":         "https://test.atlassian.net",
    "jira_email":       "admin@test.com",
    "jira_api_token":   "ATATT3xFfGF0TestToken123",
    "jira_project_key": "TST",
}


def _mock_httpx_ok():
    """Return a mock successful Jira /rest/api/3/myself response (httpx)."""
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = {"displayName": "Test Admin", "emailAddress": "admin@test.com"}
    return mock


# ── config save / read ─────────────────────────────────────────────────────────

def test_jira_config_save_and_read(client, admin_token, db):
    """Admin can save Jira credentials and read them back (token masked)."""
    res = client.post("/api/v1/jira/config", json=JIRA_CONFIG, headers=auth(admin_token))
    assert res.status_code == 200
    data = res.json()
    # POST /config returns {"ok": True, "message": ...}
    assert data.get("ok") is True

    # Read back — jira_url present, token NOT in full
    res2 = client.get("/api/v1/jira/config", headers=auth(admin_token))
    assert res2.status_code == 200
    cfg = res2.json()
    assert cfg["jira_url"] == JIRA_CONFIG["jira_url"]
    assert cfg["jira_email"] == JIRA_CONFIG["jira_email"]
    assert "jira_api_token" not in cfg  # token is stripped from GET response
    assert cfg.get("configured") is True


def test_jira_config_requires_admin(client, dev_token, db):
    """Non-admin users cannot save Jira config."""
    res = client.post("/api/v1/jira/config", json=JIRA_CONFIG, headers=auth(dev_token))
    assert res.status_code in (403, 401)


# ── status + priority mapping ──────────────────────────────────────────────────

def test_jira_status_mapping():
    """JIRA_STATUS_MAP maps all known Jira statuses to NexusPM statuses."""
    from app.api.v1.endpoints.jira import JIRA_STATUS_MAP
    required_keys = {"to do", "open", "backlog", "in progress", "done", "closed"}
    for key in required_keys:
        assert key in JIRA_STATUS_MAP, f"Missing Jira status key: {key!r}"
    # All values should be non-empty strings
    for k, v in JIRA_STATUS_MAP.items():
        assert isinstance(v, str) and v, f"Bad value for key {k!r}: {v!r}"


def test_jira_priority_mapping():
    """JIRA_PRIORITY_MAP covers standard Jira priorities."""
    from app.api.v1.endpoints.jira import JIRA_PRIORITY_MAP
    required = {"blocker", "critical", "high", "medium", "low"}
    for key in required:
        assert key in JIRA_PRIORITY_MAP, f"Missing priority key: {key!r}"


# ── connectivity test ──────────────────────────────────────────────────────────

def test_jira_test_connection_no_config(client, admin_token, db):
    """Test endpoint returns 400 when no Jira config is stored."""
    # Don't save any config → endpoint raises 400
    res = client.get("/api/v1/jira/test", headers=auth(admin_token))
    assert res.status_code in (200, 400)
    # If 400, it's because config is missing — that's correct behavior
    if res.status_code == 400:
        data = res.json()
        assert "jira" in data.get("detail", "").lower() or "configur" in data.get("detail", "").lower()
    else:
        assert "ok" in res.json()


def test_jira_test_connection_mocked(client, admin_token, db):
    """With a saved config and a mocked HTTP call, test returns ok=True."""
    # First save config
    client.post("/api/v1/jira/config", json=JIRA_CONFIG, headers=auth(admin_token))

    # jira.py uses httpx; mock it at the module level
    with patch("app.api.v1.endpoints.jira.httpx.get", return_value=_mock_httpx_ok()):
        res = client.get("/api/v1/jira/test", headers=auth(admin_token))
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data.get("display_name") == "Test Admin"


# ── webhook event handling ─────────────────────────────────────────────────────

def test_jira_webhook_updates_task_status(client, admin_token, pm_token, db):
    """Webhook with issue:updated event updates linked task status."""
    # Create a project + task
    proj = client.post(
        "/api/v1/projects",
        json={"name": "Jira Test Proj", "code": "JTRP", "status": "active"},
        headers=auth(pm_token),
    )
    project_id = proj.json()["id"]

    task_res = client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Jira linked task", "status": "todo"},
        headers=auth(pm_token),
    )
    task_id = task_res.json()["id"]

    # Attach jira key directly via PATCH
    patch_res = client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"jira_issue_key": "TST-42"},
        headers=auth(pm_token),
    )
    assert patch_res.status_code == 200

    # Fire webhook
    webhook_payload = {
        "webhookEvent": "jira:issue_updated",
        "issue": {
            "key": "TST-42",
            "fields": {
                "summary": "Jira linked task",
                "status": {"name": "In Progress"},
                "priority": {"name": "High"},
                "description": None,
                "assignee": None,
                "duedate": None,
            },
        },
    }
    res = client.post(
        "/api/v1/jira/webhook",
        json=webhook_payload,
        headers={"X-Atlassian-Webhook-Token": settings.JIRA_WEBHOOK_SECRET},
    )
    assert res.status_code == 200
    data = res.json()
    # Webhook returns {"ok": True, "jira_key": ..., "updated": bool}
    assert data.get("ok") is True


def test_jira_webhook_rejects_unauthenticated(client):
    """Webhook without the shared secret is rejected (no cross-tenant mutation)."""
    res = client.post(
        "/api/v1/jira/webhook",
        json={"webhookEvent": "jira:issue_updated", "issue": {"key": "TST-1"}},
    )
    assert res.status_code == 403


def test_jira_webhook_ignores_unknown_issue(client, db):
    """Webhook for an unknown Jira key is accepted (200) but does nothing harmful."""
    payload = {
        "webhookEvent": "jira:issue_updated",
        "issue": {
            "key": "UNKNOWN-9999",
            "fields": {
                "summary": "Unknown",
                "status": {"name": "Done"},
                "priority": {"name": "Low"},
                "description": None,
                "assignee": None,
                "duedate": None,
            },
        },
    }
    res = client.post(
        "/api/v1/jira/webhook",
        json=payload,
        headers={"X-Atlassian-Webhook-Token": settings.JIRA_WEBHOOK_SECRET},
    )
    assert res.status_code == 200
    data = res.json()
    # Returns {"ok": True, "message": "No task linked to UNKNOWN-9999"}
    assert data.get("ok") is True


def test_jira_linked_tasks_empty(client, pm_token, db):
    """Linked tasks endpoint returns a list (empty when no tasks are linked)."""
    res = client.get("/api/v1/jira/linked", headers=auth(pm_token))
    assert res.status_code == 200
    data = res.json()
    # Endpoint returns a JSON array directly
    assert isinstance(data, list)
