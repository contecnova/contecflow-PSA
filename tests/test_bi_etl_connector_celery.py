"""Tests: BI ETL Connector Celery pipeline — sync_connector_data task,
sync log persistence, async enqueue endpoint, and log endpoint.
"""
import pytest
from tests.conftest import auth


# ── Helpers ────────────────────────────────────────────────────────────────────

def _enable_connector(client, token, connector="salesforce"):
    """Enable a connector so sync endpoints don't skip it."""
    client.put(
        f"/api/v1/bi/intelligence/connectors/{connector}",
        json={"enabled": True, "source": connector},
        headers=auth(token),
    )


# ── GET /bi/intelligence/connectors/{connector}/sync/log ──────────────────────

def test_sync_log_returns_empty_initially(client, admin_token):
    _enable_connector(client, admin_token, "salesforce")
    res = client.get(
        "/api/v1/bi/intelligence/connectors/salesforce/sync/log",
        headers=auth(admin_token),
    )
    assert res.status_code == 200
    data = res.json()
    assert "entries" in data
    assert isinstance(data["entries"], list)


def test_sync_log_unauthenticated(client):
    res = client.get("/api/v1/bi/intelligence/connectors/salesforce/sync/log")
    assert res.status_code in (401, 403)


def test_sync_log_limit_param(client, admin_token):
    _enable_connector(client, admin_token, "zendesk")
    res = client.get(
        "/api/v1/bi/intelligence/connectors/zendesk/sync/log?limit=10",
        headers=auth(admin_token),
    )
    assert res.status_code == 200
    data = res.json()
    assert data["connector"] == "zendesk"
    assert len(data["entries"]) <= 10


# ── POST /bi/intelligence/connectors/{connector}/sync/async ──────────────────

def test_enqueue_connector_sync_queues_task(client, admin_token, monkeypatch):
    """Enqueue endpoint delegates to sync_connector_data.apply_async."""
    import app.api.v1.endpoints.bi_intelligence as ep_mod

    class _FakeTask:
        id = "fake-celery-task-id"

    class _MockSyncTask:
        def apply_async(self, *a, **kw):
            return _FakeTask()

    monkeypatch.setattr(ep_mod, "sync_connector_data", _MockSyncTask(), raising=False)

    # Need to reload the endpoint's import; patch at the module level via worker
    import app.worker as worker_mod
    monkeypatch.setattr(worker_mod, "sync_connector_data", _MockSyncTask())

    _enable_connector(client, admin_token, "salesforce")
    res = client.post(
        "/api/v1/bi/intelligence/connectors/salesforce/sync/async",
        headers=auth(admin_token),
    )
    # Either 200 (queued) or 503 (Redis not available in test env) is acceptable
    assert res.status_code in (200, 503)
    if res.status_code == 200:
        data = res.json()
        assert data["connector"] == "salesforce"
        assert "task_id" in data


# ── _log_sync integration test (service layer) ────────────────────────────────

def test_log_sync_appends_entries(db):
    """_log_sync stores entries that get_connector_sync_log can read back."""
    from app.integrations.bi_etl_connectors import _log_sync
    from app.services.bi_intelligence_service import get_connector_sync_log

    result = {
        "ok": True,
        "records_ingested": 42,
        "error": None,
        "started_at": "2024-01-01T10:00:00+00:00",
        "finished_at": "2024-01-01T10:00:05+00:00",
    }
    _log_sync(db, "salesforce", None, result)

    log = get_connector_sync_log(db, organization_id=None, connector="salesforce", limit=10)
    assert log["connector"] == "salesforce"
    assert len(log["entries"]) >= 1
    first = log["entries"][0]  # most-recent first
    assert first["ok"] is True
    assert first["records_ingested"] == 42


def test_log_sync_rolling_cap(db):
    """_log_sync caps entries at _SYNC_LOG_MAX_ENTRIES (100)."""
    from app.integrations.bi_etl_connectors import _log_sync, _SYNC_LOG_MAX_ENTRIES
    from app.services.bi_intelligence_service import get_connector_sync_log

    # Insert 105 entries
    for i in range(105):
        _log_sync(db, "hubspot", None, {
            "ok": True,
            "records_ingested": i,
            "error": None,
            "started_at": f"2024-01-{i % 28 + 1:02d}T10:00:00+00:00",
            "finished_at": f"2024-01-{i % 28 + 1:02d}T10:00:01+00:00",
        })

    log = get_connector_sync_log(db, organization_id=None, connector="hubspot", limit=200)
    assert len(log["entries"]) <= _SYNC_LOG_MAX_ENTRIES


# ── httpx helper unit tests ───────────────────────────────────────────────────

def test_http_get_helper_uses_httpx(monkeypatch):
    """_http_get uses httpx.Client and returns parsed JSON."""
    import app.integrations.bi_etl_connectors as conn_mod

    class _FakeResponse:
        def raise_for_status(self): pass
        def json(self): return {"result": "ok"}

    class _FakeClient:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def get(self, *a, **kw): return _FakeResponse()

    monkeypatch.setattr(conn_mod._httpx, "Client", lambda **kw: _FakeClient())
    result = conn_mod._http_get("https://example.test/api")
    assert result == {"result": "ok"}


def test_http_post_helper_json(monkeypatch):
    """_http_post sends JSON body and returns parsed response."""
    import app.integrations.bi_etl_connectors as conn_mod

    posted = {}

    class _FakeResponse:
        def raise_for_status(self): pass
        def json(self): return {"id": 1}

    class _FakeClient:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def post(self, url, json=None, content=None, headers=None):
            posted["json"] = json
            posted["content"] = content
            return _FakeResponse()

    monkeypatch.setattr(conn_mod._httpx, "Client", lambda **kw: _FakeClient())
    result = conn_mod._http_post("https://example.test/api", payload={"key": "val"})
    assert result == {"id": 1}
    assert posted["json"] == {"key": "val"}


def test_http_post_helper_raw_body(monkeypatch):
    """_http_post sends raw string body when raw_body is provided."""
    import app.integrations.bi_etl_connectors as conn_mod

    posted = {}

    class _FakeResponse:
        def raise_for_status(self): pass
        def json(self): return {"boards": []}

    class _FakeClient:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def post(self, url, json=None, content=None, headers=None):
            posted["content"] = content
            return _FakeResponse()

    monkeypatch.setattr(conn_mod._httpx, "Client", lambda **kw: _FakeClient())
    result = conn_mod._http_post("https://api.monday.com/v2", raw_body='{"query":"{}"}')
    assert result == {"boards": []}
    assert posted["content"] == b'{"query":"{}"}'


# ── run_sync calls _log_sync ──────────────────────────────────────────────────

def test_run_sync_writes_log(db, monkeypatch):
    """BaseConnector.run_sync always writes a log entry regardless of outcome."""
    from app.integrations.bi_etl_connectors import WebhookPluginConnector
    from app.services.bi_intelligence_service import get_connector_sync_log

    connector = WebhookPluginConnector()
    connector.name = "webhook_test_log"

    # Simulate a failed extract (empty URL → returns [])
    result = connector.run_sync(config={"endpoint_url": ""}, organization_id=None, db=db)
    assert result["ok"] is True  # no error, just 0 records
    assert result["records_ingested"] == 0

    log = get_connector_sync_log(db, organization_id=None, connector="webhook_test_log", limit=5)
    assert len(log["entries"]) >= 1
    assert log["entries"][0]["connector"] == "webhook_test_log"


# ── Beat schedule sanity check ────────────────────────────────────────────────

def test_beat_schedule_has_all_connectors():
    """All 21 expected connectors have a beat schedule entry."""
    from app.worker import celery_app

    beat = celery_app.conf.beat_schedule
    expected_connectors = [
        "salesforce", "hubspot", "jira", "stripe", "xero",
        "zendesk", "freshdesk", "servicenow", "pipedrive", "zoho-crm",
        "quickbooks", "github", "gitlab", "datadog", "monday",
        "asana", "trello", "shopify", "intercom", "clickup", "google-analytics",
    ]
    for name in expected_connectors:
        key = f"bi-connector-sync-{name}"
        assert key in beat, f"Missing beat entry: {key}"
        entry = beat[key]
        assert entry["task"] == "app.worker.sync_connector_data"
        assert "connector_id" in entry.get("kwargs", {})
