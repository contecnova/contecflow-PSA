"""Tests de resource forecasting."""
from tests.conftest import auth

def test_forecast_summary(client, admin_token, db):
    res = client.get("/api/v1/resource-forecast/summary", params={"weeks": 4}, headers=auth(admin_token))
    assert res.status_code == 200
    data = res.json()
    assert "total_users" in data
    assert "avg_team_load_pct" in data
    assert "weeks" in data

def test_forecast_heatmap(client, admin_token, db):
    res = client.get("/api/v1/resource-forecast/weeks", params={"weeks": 4}, headers=auth(admin_token))
    assert res.status_code == 200
    data = res.json()
    assert "users" in data
    assert "week_labels" in data
    assert len(data["week_labels"]) == 4

def test_forecast_availability(client, admin_token, db):
    res = client.get("/api/v1/resource-forecast/availability", params={"hours_needed": 20}, headers=auth(admin_token))
    assert res.status_code == 200
    data = res.json()
    assert "candidates" in data
    assert "insufficient" in data

def test_forecast_user_detail(client, admin_token, db):
    res = client.get("/api/v1/resource-forecast/users/admin-test-id", params={"weeks": 4}, headers=auth(admin_token))
    assert res.status_code in (200, 404)
    if res.status_code == 200:
        assert "weeks" in res.json()

def test_forecast_requires_manager(client, dev_token, db):
    res = client.get("/api/v1/resource-forecast/summary", headers=auth(dev_token))
    assert res.status_code in (401, 403)
