"""Tests del planificador de capacidad."""
from tests.conftest import auth
from datetime import date, timedelta
from app.models.financial import CapacityPlan

def next_monday():
    today = date.today()
    return str(today + timedelta(days=(7 - today.weekday())))

def test_capacity_board_empty(client, admin_token, db):
    res = client.get("/api/v1/capacity/board", headers=auth(admin_token))
    assert res.status_code == 200
    assert isinstance(res.json()["items"], list)

def test_create_capacity_plan(client, pm_token, db):
    res = client.post("/api/v1/capacity/plans", json={
        "user_id": "pm-test-id",
        "week_start": next_monday(),
        "planned_hours": 32,
    }, headers=auth(pm_token))
    assert res.status_code in (200, 201)
    data = res.json()["data"]
    assert "id" in data

def test_move_capacity_plan(client, pm_token, db):
    plan = client.post("/api/v1/capacity/plans", json={
        "user_id": "pm-test-id",
        "week_start": next_monday(),
        "planned_hours": 20,
    }, headers=auth(pm_token)).json()["data"]
    new_week = str(date.today() + timedelta(days=14))
    res = client.patch(f"/api/v1/capacity/plans/{plan['id']}", json={"week_start": new_week}, headers=auth(pm_token))
    assert res.status_code == 200

def test_delete_capacity_plan(client, pm_token, db):
    plan = client.post("/api/v1/capacity/plans", json={
        "user_id": "pm-test-id", "week_start": next_monday(), "planned_hours": 10,
    }, headers=auth(pm_token)).json()["data"]
    res = client.delete(f"/api/v1/capacity/plans/{plan['id']}", headers=auth(pm_token))
    assert res.status_code == 200
    payload = res.json()["data"]
    assert payload.get("ok") is True

    board = client.get("/api/v1/capacity/board", headers=auth(pm_token))
    assert board.status_code == 200
    ids = [item["id"] for item in board.json()["items"]]
    assert plan["id"] not in ids

    row = db.query(CapacityPlan).filter(CapacityPlan.id == plan["id"]).first()
    assert row is not None
    assert row.is_active is False

def test_capacity_board_with_range(client, admin_token, db):
    today = str(date.today())
    future = str(date.today() + timedelta(weeks=4))
    res = client.get("/api/v1/capacity/board", params={"week_from": today, "week_to": future}, headers=auth(admin_token))
    assert res.status_code == 200
