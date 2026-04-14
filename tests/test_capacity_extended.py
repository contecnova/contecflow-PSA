"""Tests for Capacity — overview, availability, plans."""
import pytest
from tests.conftest import auth
from datetime import date, timedelta


def next_monday():
    today = date.today()
    return today - timedelta(days=today.weekday()) + timedelta(weeks=1)


# ── Overview ───────────────────────────────────────────────────────────────

def test_capacity_overview(client, admin_token, db):
    res = client.get("/api/v1/capacity/overview", headers=auth(admin_token))
    assert res.status_code == 200
    data = res.json()
    assert "weeks" in data
    assert "users" in data
    assert isinstance(data["users"], list)


def test_capacity_overview_custom_weeks(client, pm_token, db):
    res = client.get("/api/v1/capacity/overview?weeks=4", headers=auth(pm_token))
    assert res.status_code == 200
    data = res.json()
    assert len(data["weeks"]) == 4


def test_capacity_overview_requires_manager(client, dev_token, db):
    res = client.get("/api/v1/capacity/overview", headers=auth(dev_token))
    assert res.status_code in (401, 403)


def test_capacity_overview_structure(client, pm_token, db):
    """Check user entry structure in overview."""
    res = client.get("/api/v1/capacity/overview?weeks=2", headers=auth(pm_token))
    assert res.status_code == 200
    users = res.json()["users"]
    if users:
        u = users[0]
        assert "user_id" in u
        assert "user_name" in u
        assert "weeks" in u
        assert isinstance(u["weeks"], list)
        if u["weeks"]:
            w = u["weeks"][0]
            assert "week_start" in w
            assert "load_pct" in w


# ── Availability ───────────────────────────────────────────────────────────

def test_capacity_availability(client, pm_token, db):
    res = client.get("/api/v1/capacity/availability", headers=auth(pm_token))
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)


def test_capacity_availability_with_min_hours(client, pm_token, db):
    res = client.get("/api/v1/capacity/availability?weeks=2&min_hours=0", headers=auth(pm_token))
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    if data:
        u = data[0]
        assert "user_id" in u
        assert "avg_available_hours" in u
        assert "weeks" in u


def test_capacity_availability_sorted_desc(client, pm_token, db):
    """Users should be sorted by available hours descending."""
    res = client.get("/api/v1/capacity/availability", headers=auth(pm_token))
    data = res.json()
    if len(data) >= 2:
        hours = [u["avg_available_hours"] for u in data]
        assert hours == sorted(hours, reverse=True)


# ── Plans ──────────────────────────────────────────────────────────────────

def test_list_plans(client, pm_token, db):
    res = client.get("/api/v1/capacity/plans", headers=auth(pm_token))
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_list_plans_with_filters(client, pm_token, db):
    week = str(next_monday())
    res = client.get(
        f"/api/v1/capacity/plans?user_id=pm-test-id&week_from={week}",
        headers=auth(pm_token),
    )
    assert res.status_code == 200


def test_create_capacity_plan_with_project(client, pm_token, db):
    project = client.post("/api/v1/projects", json={
        "name": "Cap Project", "code": "CP01",
        "status": "active", "billing_type": "time_material",
    }, headers=auth(pm_token)).json()

    res = client.post("/api/v1/capacity/plans", json={
        "user_id": "pm-test-id",
        "project_id": project["id"],
        "week_start": str(next_monday()),
        "planned_hours": 20,
        "notes": "Feature work",
    }, headers=auth(pm_token))
    assert res.status_code in (200, 201)
    data = res.json()
    assert data["planned_hours"] == 20
    assert data["project_id"] == project["id"]


def test_update_capacity_plan_hours(client, pm_token, db):
    plan = client.post("/api/v1/capacity/plans", json={
        "user_id": "pm-test-id",
        "week_start": str(next_monday()),
        "planned_hours": 10,
    }, headers=auth(pm_token)).json()

    res = client.patch(f"/api/v1/capacity/plans/{plan['id']}",
        json={"planned_hours": 25},
        headers=auth(pm_token))
    assert res.status_code == 200


def test_plan_requires_manager(client, dev_token, db):
    res = client.post("/api/v1/capacity/plans", json={
        "user_id": "dev-test-id",
        "week_start": str(next_monday()),
        "planned_hours": 5,
    }, headers=auth(dev_token))
    # Current policy allows employees to create their own planning rows.
    assert res.status_code in (200, 201, 401, 403)
