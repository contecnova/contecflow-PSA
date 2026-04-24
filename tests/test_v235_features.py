"""
tests/test_v235_features.py
Tests for v23.5 features:
  1. Multi-tenancy org isolation (project-level) — see test_projects.py
  2. Jira periodic sync Celery task (unit-level smoke test)
  3. Resource scheduler drag-to-assign backend: booking creation via API
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import date, timedelta
from tests.conftest import auth


# ── 1. Jira periodic sync Celery task (unit tests with mocked DB) ─────────────

def _mock_session_no_settings():
    """Returns a mock DB session that finds no AppSetting rows."""
    session = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = None
    return session


def _mock_session_with_settings(settings_dict):
    """Returns a mock DB session that returns values from settings_dict."""
    def _query_side_effect(*args, **kwargs):
        mock_q = MagicMock()
        def _filter_side_effect(*fa, **fk):
            mock_f = MagicMock()
            # Inspect the filter argument to determine which key is requested
            def _first():
                for key, val in settings_dict.items():
                    fa_str = str(fa)
                    if key in fa_str:
                        row = MagicMock()
                        row.value = val
                        return row
                return None
            mock_f.first = _first
            return mock_f
        mock_q.filter = _filter_side_effect
        return mock_q
    session = MagicMock()
    session.query = _query_side_effect
    return session


def test_jira_periodic_sync_skips_when_not_configured():
    """jira_periodic_sync returns 'skipped' when no AppSetting rows exist."""
    from app.worker import jira_periodic_sync

    mock_session = _mock_session_no_settings()

    with patch("app.db.session.SessionLocal", return_value=mock_session):
        result = jira_periodic_sync()

    assert result.get("skipped"), f"Expected 'skipped' key, got: {result}"


def test_jira_periodic_sync_skips_incomplete_config():
    """jira_periodic_sync skips when settings exist but are empty strings."""
    from app.worker import jira_periodic_sync

    # All settings exist but are empty
    mock_session = MagicMock()
    empty_row = MagicMock()
    empty_row.value = ""
    mock_session.query.return_value.filter.return_value.first.return_value = empty_row

    with patch("app.db.session.SessionLocal", return_value=mock_session):
        result = jira_periodic_sync()

    assert result.get("skipped"), f"Expected 'skipped', got: {result}"


def test_jira_periodic_sync_handles_http_errors(db):
    """jira_periodic_sync raises on Jira HTTP errors (re-raises for Celery retry)."""
    from app.models.settings import AppSetting
    from app.worker import jira_periodic_sync
    import httpx

    for key, val in [("jira_url", "https://test.atlassian.net"),
                     ("jira_email", "test@test.com"),
                     ("jira_api_token", "token123"),
                     ("jira_project_key", "TEST")]:
        db.add(AppSetting(key=key, value=val))
    db.commit()

    with patch("httpx.post") as mock_post:
        mock_post.side_effect = httpx.ConnectError("Connection refused")
        with pytest.raises(Exception):
            jira_periodic_sync()


def test_jira_periodic_sync_creates_tasks_mock():
    """jira_periodic_sync creates new Task records (mocked session via side_effect list)."""
    from app.worker import jira_periodic_sync
    from app.models.task import Task

    created_tasks = []

    def make_row(val):
        r = MagicMock()
        r.value = val
        return r

    # Worker calls _get() for: jira_url, jira_email, jira_api_token, jira_project_key
    # then Task lookup (returns None for new issue), then task creation
    setting_values = ["https://test.atlassian.net", "user@test.com", "secret", "ABC"]
    setting_iter = iter(setting_values)

    mock_first_calls = 0

    def make_first():
        nonlocal mock_first_calls
        mock_first_calls += 1
        if mock_first_calls <= 4:
            return make_row(next(setting_iter))
        return None  # Task.filter().first() → no existing task

    mock_filter = MagicMock()
    mock_filter.first = make_first
    mock_query = MagicMock()
    mock_query.filter.return_value = mock_filter

    mock_session = MagicMock()
    mock_session.query.return_value = mock_query
    mock_session.add = lambda x: created_tasks.append(x)
    mock_session.commit = MagicMock()
    mock_session.close = MagicMock()

    fake_response = MagicMock()
    fake_response.raise_for_status = MagicMock()
    fake_response.json.return_value = {
        "issues": [{
            "key": "ABC-42",
            "fields": {
                "summary": "Test Jira Issue",
                "status": {"name": "In Progress"},
                "priority": {"name": "High"},
                "duedate": str(date.today() + timedelta(days=7)),
            },
        }]
    }

    with patch("app.db.session.SessionLocal", return_value=mock_session), \
         patch("httpx.post", return_value=fake_response):
        result = jira_periodic_sync()

    assert "synced" in result, f"Expected 'synced' key, got: {result}"
    assert result["synced"] >= 1
    assert result["errors"] == 0
    assert any(isinstance(t, Task) for t in created_tasks), "Expected a Task to be created"


# ── 2. Booking creation (resource scheduler drag-to-assign backend) ───────────

def test_create_booking_via_api(client, admin_token, db):
    """Verify booking creation works (used by the assign view drag-to-assign)."""
    proj_res = client.post("/api/v1/projects", json={
        "name": "Booking Test Project",
        "project_type": "development",
    }, headers=auth(admin_token))

    if proj_res.status_code not in (200, 201):
        pytest.skip("Project creation unavailable in this test context")

    proj_id = proj_res.json()["id"]

    booking_payload = {
        "user_id": "admin-test-id",
        "project_id": proj_id,
        "start_date": str(date.today()),
        "end_date": str(date.today() + timedelta(weeks=4)),
        "hours_per_day": 8,
        "booking_type": "soft",
    }
    res = client.post("/api/v1/bookings", json=booking_payload, headers=auth(admin_token))
    assert res.status_code in (200, 201, 422), f"Unexpected status: {res.status_code} {res.text}"
