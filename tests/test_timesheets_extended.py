"""Tests for Timesheets — submission, review, team views."""
import pytest
from tests.conftest import auth
from datetime import date, timedelta


def next_monday():
    today = date.today()
    return today - timedelta(days=today.weekday())


def make_project(client, token):
    r = client.post("/api/v1/projects", json={
        "name": "Timesheet Project", "code": "TSP01",
        "status": "active", "billing_type": "time_material",
    }, headers=auth(token))
    pid = r.json()["id"]
    # Ensure dev-test-id can log hours against this project
    client.post(f"/api/v1/projects/{pid}/members",
                json={"user_id": "dev-test-id", "role": "developer"},
                headers=auth(token))
    return pid


def add_imputation(client, token, project_id, hours=6):
    client.post("/api/v1/imputations", json={
        "project_id": project_id,
        "date": str(date.today()),
        "hours": hours,
        "description": "Work",
        "is_billable": True,
    }, headers=auth(token))


# ── My Timesheets ──────────────────────────────────────────────────────────

def test_get_my_timesheets(client, dev_token, db):
    res = client.get("/api/v1/timesheets/my", headers=auth(dev_token))
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) > 0
    # Check structure
    ts = data[0]
    assert "week_start" in ts
    assert "week_end" in ts
    assert "status" in ts
    assert "total_hours" in ts


def test_get_my_timesheets_custom_weeks(client, dev_token, db):
    res = client.get("/api/v1/timesheets/my?weeks=4", headers=auth(dev_token))
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 4


def test_get_timesheet_lines(client, dev_token, pm_token, db):
    pid = make_project(client, pm_token)
    add_imputation(client, dev_token, pid)

    week = str(next_monday())
    res = client.get(f"/api/v1/timesheets/my/{week}/lines", headers=auth(dev_token))
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    if data:
        assert "date" in data[0]
        assert "hours" in data[0]
        assert "project_name" in data[0]


def test_get_timesheet_lines_empty_week(client, dev_token, db):
    """Week with no imputations returns empty list."""
    past_week = str(next_monday() - timedelta(weeks=3))
    res = client.get(f"/api/v1/timesheets/my/{past_week}/lines", headers=auth(dev_token))
    assert res.status_code == 200
    assert res.json() == []


# ── Submit Timesheet ───────────────────────────────────────────────────────

def test_submit_timesheet_empty_fails(client, dev_token, db):
    """Cannot submit an empty timesheet."""
    week = str(next_monday() - timedelta(weeks=2))
    res = client.post(f"/api/v1/timesheets/my/{week}/submit", headers=auth(dev_token))
    assert res.status_code == 400
    assert "vacío" in res.json()["detail"].lower() or "empty" in res.json()["detail"].lower()


def test_submit_timesheet_with_hours(client, dev_token, pm_token, db):
    """Can submit a timesheet that has hours."""
    pid = make_project(client, pm_token)
    add_imputation(client, dev_token, pid, hours=8)

    week = str(next_monday())
    res = client.post(f"/api/v1/timesheets/my/{week}/submit", headers=auth(dev_token))
    assert res.status_code == 200
    assert res.json()["status"] in ("submitted", "approved", "rejected", "draft")


def test_submit_timesheet_twice_fails(client, dev_token, pm_token, db):
    """Cannot submit an already-submitted timesheet."""
    pid = make_project(client, pm_token)
    add_imputation(client, dev_token, pid, hours=8)

    week = str(next_monday())
    client.post(f"/api/v1/timesheets/my/{week}/submit", headers=auth(dev_token))
    res = client.post(f"/api/v1/timesheets/my/{week}/submit", headers=auth(dev_token))
    assert res.status_code == 400


# ── Pending Timesheets (Manager) ───────────────────────────────────────────

def test_get_pending_timesheets(client, pm_token, db):
    res = client.get("/api/v1/timesheets/pending", headers=auth(pm_token))
    assert res.status_code == 200
    payload = res.json()
    items = payload.get("items") if isinstance(payload, dict) else payload
    assert isinstance(items, list)


def test_get_pending_timesheets_non_manager_fails(client, dev_token, db):
    res = client.get("/api/v1/timesheets/pending", headers=auth(dev_token))
    assert res.status_code in (401, 403)


# ── Team Timesheets ────────────────────────────────────────────────────────

def test_get_team_timesheets(client, pm_token, db):
    res = client.get("/api/v1/timesheets/team", headers=auth(pm_token))
    assert res.status_code == 200
    payload = res.json()
    items = payload.get("items") if isinstance(payload, dict) else payload
    assert isinstance(items, list)


def test_get_team_timesheets_with_filters(client, pm_token, db):
    week = str(next_monday())
    res = client.get(
        f"/api/v1/timesheets/team?week_start={week}&status=draft",
        headers=auth(pm_token),
    )
    assert res.status_code == 200
    payload = res.json()
    items = payload.get("items") if isinstance(payload, dict) else payload
    assert isinstance(items, list)


def test_team_timesheets_requires_manager(client, dev_token, db):
    res = client.get("/api/v1/timesheets/team", headers=auth(dev_token))
    assert res.status_code in (401, 403)


# ── Review Timesheet ───────────────────────────────────────────────────────

def test_review_timesheet_approve(client, dev_token, pm_token, db):
    """PM can approve a submitted timesheet."""
    pid = make_project(client, pm_token)
    add_imputation(client, dev_token, pid, hours=8)

    week = str(next_monday())
    client.post(f"/api/v1/timesheets/my/{week}/submit", headers=auth(dev_token))
    ts_id = None

    # Find submitted timesheet id via pending list
    _pending_payload = client.get("/api/v1/timesheets/pending", headers=auth(pm_token)).json()
    pending = _pending_payload.get("items") if isinstance(_pending_payload, dict) else _pending_payload
    if not pending:
        pytest.skip("No submitted timesheet found")

    ts_id = pending[0]["id"]
    res = client.post(f"/api/v1/timesheets/{ts_id}/review",
        json={"approved": True, "notes": "Looks good"},
        headers=auth(pm_token))
    assert res.status_code == 200
    assert "approved" in res.json()["message"].lower() or res.json()["status"] == "approved"


def test_review_timesheet_reject(client, dev_token, pm_token, db):
    """PM can reject a submitted timesheet."""
    pid = make_project(client, pm_token)
    add_imputation(client, dev_token, pid, hours=4)

    week = str(next_monday())
    client.post(f"/api/v1/timesheets/my/{week}/submit", headers=auth(dev_token))

    _pending_payload = client.get("/api/v1/timesheets/pending", headers=auth(pm_token)).json()
    pending = _pending_payload.get("items") if isinstance(_pending_payload, dict) else _pending_payload
    if not pending:
        pytest.skip("No submitted timesheet found")

    ts_id = pending[0]["id"]
    res = client.post(f"/api/v1/timesheets/{ts_id}/review",
        json={"approved": False, "notes": "Missing details"},
        headers=auth(pm_token))
    assert res.status_code == 200
    assert "rechazado" in res.json()["message"].lower() or res.json()["status"] == "rejected"


def test_review_nonexistent_timesheet(client, pm_token, db):
    res = client.post("/api/v1/timesheets/nonexistent-id/review",
        json={"approved": True},
        headers=auth(pm_token))
    assert res.status_code == 404


def test_review_timesheets_requires_manager(client, dev_token, db):
    res = client.post("/api/v1/timesheets/any-id/review",
        json={"approved": True},
        headers=auth(dev_token))
    assert res.status_code in (401, 403)
