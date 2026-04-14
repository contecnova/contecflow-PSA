"""Extended tests for Profitability — milestones CRUD, summary, by-person/week."""
import pytest
from tests.conftest import auth
from datetime import date, timedelta


def make_project(client, token, code="PRF01"):
    r = client.post("/api/v1/projects", json={
        "name": f"Profit Project {code}", "code": code,
        "status": "active", "billing_type": "time_material",
        "budget_amount": 50000, "billing_rate": 150,
    }, headers=auth(token))
    return r.json()["id"]


# ── Summary ────────────────────────────────────────────────────────────────

def test_profitability_summary_structure(client, admin_token, pm_token, db):
    make_project(client, pm_token, "PRF02")
    res = client.get("/api/v1/profitability/summary", headers=auth(admin_token))
    assert res.status_code == 200
    data = res.json()
    assert "projects" in data
    assert "portfolio" in data
    portfolio = data["portfolio"]
    assert "total_cost" in portfolio
    assert "total_margin" in portfolio
    assert "project_count" in portfolio


def test_profitability_summary_with_status_filter(client, admin_token, db):
    res = client.get("/api/v1/profitability/summary?status=active", headers=auth(admin_token))
    assert res.status_code == 200


def test_profitability_summary_requires_admin(client, pm_token, db):
    res = client.get("/api/v1/profitability/summary", headers=auth(pm_token))
    assert res.status_code in (401, 403)


# ── Project Detail ─────────────────────────────────────────────────────────

def test_profitability_detail_has_breakdowns(client, pm_token, db):
    pid = make_project(client, pm_token, "PRF03")
    res = client.get(f"/api/v1/profitability/{pid}", headers=auth(pm_token))
    assert res.status_code == 200
    data = res.json()
    assert "by_person" in data
    assert "by_week" in data
    assert "milestones" in data
    assert isinstance(data["by_person"], list)
    assert isinstance(data["by_week"], list)
    assert isinstance(data["milestones"], list)


def test_profitability_employee_rejected(client, dev_token, pm_token, db):
    pid = make_project(client, pm_token, "PRF04")
    res = client.get(f"/api/v1/profitability/{pid}", headers=auth(dev_token))
    assert res.status_code in (401, 403)


def test_profitability_not_found(client, pm_token, db):
    res = client.get("/api/v1/profitability/nonexistent-id", headers=auth(pm_token))
    assert res.status_code == 404


# ── Milestones ─────────────────────────────────────────────────────────────

def test_list_milestones_empty(client, pm_token, db):
    pid = make_project(client, pm_token, "PRF05")
    res = client.get(f"/api/v1/profitability/{pid}/milestones", headers=auth(pm_token))
    assert res.status_code == 200
    assert res.json() == []


def test_create_milestone(client, pm_token, db):
    pid = make_project(client, pm_token, "PRF06")
    res = client.post(f"/api/v1/profitability/{pid}/milestones", json={
        "name": "Phase 1 Complete",
        "due_date": str(date.today() + timedelta(days=30)),
        "billing_amount": 10000,
        "billing_pct": 25,
        "sort_order": 1,
    }, headers=auth(pm_token))
    assert res.status_code in (200, 201)
    data = res.json()
    assert data["name"] == "Phase 1 Complete"
    assert data["billing_amount"] == 10000


def test_create_milestone_employee_rejected(client, dev_token, pm_token, db):
    pid = make_project(client, pm_token, "PRF07")
    res = client.post(f"/api/v1/profitability/{pid}/milestones", json={
        "name": "Forbidden Milestone",
    }, headers=auth(dev_token))
    assert res.status_code in (401, 403)


def test_update_milestone(client, pm_token, db):
    pid = make_project(client, pm_token, "PRF08")
    m = client.post(f"/api/v1/profitability/{pid}/milestones", json={
        "name": "Original Name",
        "billing_amount": 5000,
    }, headers=auth(pm_token)).json()

    today = str(date.today())
    res = client.patch(f"/api/v1/profitability/{pid}/milestones/{m['id']}", json={
        "is_completed": True,
        "completed_date": today,
        "name": "Updated Name",
    }, headers=auth(pm_token))
    assert res.status_code == 200
    data = res.json()
    assert data["is_completed"] is True


def test_update_milestone_not_found(client, pm_token, db):
    pid = make_project(client, pm_token, "PRF09")
    res = client.patch(f"/api/v1/profitability/{pid}/milestones/nonexistent", json={
        "is_completed": True,
    }, headers=auth(pm_token))
    assert res.status_code == 404


def test_delete_milestone(client, pm_token, db):
    pid = make_project(client, pm_token, "PRF10")
    m = client.post(f"/api/v1/profitability/{pid}/milestones", json={
        "name": "To Delete",
    }, headers=auth(pm_token)).json()

    res = client.delete(f"/api/v1/profitability/{pid}/milestones/{m['id']}", headers=auth(pm_token))
    assert res.status_code == 200
    assert res.json()["ok"] is True


def test_delete_milestone_not_found(client, pm_token, db):
    pid = make_project(client, pm_token, "PRF11")
    res = client.delete(f"/api/v1/profitability/{pid}/milestones/nonexistent", headers=auth(pm_token))
    assert res.status_code == 404


def test_milestone_billed_update(client, pm_token, db):
    pid = make_project(client, pm_token, "PRF12")
    m = client.post(f"/api/v1/profitability/{pid}/milestones", json={
        "name": "Invoice Milestone",
        "billing_amount": 20000,
    }, headers=auth(pm_token)).json()

    res = client.patch(f"/api/v1/profitability/{pid}/milestones/{m['id']}", json={
        "is_billed": True,
        "billed_at": str(date.today()),
    }, headers=auth(pm_token))
    assert res.status_code == 200
    assert res.json()["is_billed"] is True


def test_milestones_listed_in_profitability_detail(client, pm_token, db):
    pid = make_project(client, pm_token, "PRF13")
    client.post(f"/api/v1/profitability/{pid}/milestones", json={
        "name": "M1", "billing_amount": 1000,
    }, headers=auth(pm_token))
    client.post(f"/api/v1/profitability/{pid}/milestones", json={
        "name": "M2", "billing_amount": 2000,
    }, headers=auth(pm_token))

    res = client.get(f"/api/v1/profitability/{pid}", headers=auth(pm_token))
    data = res.json()
    assert len(data["milestones"]) >= 2
