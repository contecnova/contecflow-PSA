"""Tests for Dashboard — KPIs, project health, resource load, profitability."""
from sqlalchemy import event
from tests.conftest import auth
from datetime import date, timedelta

from app.api.v1.endpoints.dashboard import get_profitability
from app.models.imputation import Imputation
from app.models.project import Project, ProjectStatus, ProjectType
from app.models.user import User


def make_project(client, token, code="DASH01"):
    r = client.post("/api/v1/projects", json={
        "name": f"Dash Project {code}", "code": code,
        "status": "active", "billing_type": "time_material",
    }, headers=auth(token))
    return r.json()["data"]["id"]


# ── KPIs ───────────────────────────────────────────────────────────────────

def test_kpis_admin(client, admin_token, db):
    res = client.get("/api/v1/dashboard/kpis", headers=auth(admin_token))
    assert res.status_code == 200
    data = res.json()["data"]
    assert "total_budget" in data
    assert "projects_active" in data
    assert "total_resources" in data
    assert "tasks_blocked" in data
    assert "tasks_overdue" in data
    assert "hours_logged_this_week" in data


def test_kpis_requires_admin(client, pm_token, db):
    res = client.get("/api/v1/dashboard/kpis", headers=auth(pm_token))
    assert res.status_code in (401, 403)


def test_kpis_with_active_project(client, admin_token, pm_token, db):
    make_project(client, pm_token)
    res = client.get("/api/v1/dashboard/kpis", headers=auth(admin_token))
    assert res.status_code == 200
    data = res.json()["data"]
    assert "projects_active" in data
    assert isinstance(data["projects_active"], int)


# ── Projects Health ────────────────────────────────────────────────────────

def test_projects_health(client, pm_token, db):
    res = client.get("/api/v1/dashboard/projects-health", headers=auth(pm_token))
    assert res.status_code == 200
    assert isinstance(res.json()["items"], list)


def test_projects_health_structure(client, pm_token, db):
    make_project(client, pm_token, code="HP01")
    res = client.get("/api/v1/dashboard/projects-health", headers=auth(pm_token))
    data = res.json()["items"]
    if data:
        p = data[0]
        assert "project_id" in p
        assert "project_name" in p
        assert "budget_used_pct" in p
        assert "risk_level" in p
        assert "alerts_count" in p


def test_projects_health_requires_manager(client, dev_token, db):
    res = client.get("/api/v1/dashboard/projects-health", headers=auth(dev_token))
    assert res.status_code in (401, 403)


# ── Resource Load ──────────────────────────────────────────────────────────

def test_resource_load(client, pm_token, db):
    res = client.get("/api/v1/dashboard/resource-load", headers=auth(pm_token))
    assert res.status_code == 200
    data = res.json()["items"]
    assert isinstance(data, list)


def test_resource_load_structure(client, pm_token, db):
    res = client.get("/api/v1/dashboard/resource-load", headers=auth(pm_token))
    data = res.json()["items"]
    if data:
        u = data[0]
        assert "user_id" in u
        assert "user_name" in u
        assert "load_pct" in u
        assert "hours_week" in u
        assert "active_projects" in u


def test_resource_load_sorted_desc(client, pm_token, db):
    """Resource load should be sorted by load_pct descending."""
    res = client.get("/api/v1/dashboard/resource-load", headers=auth(pm_token))
    data = res.json()["items"]
    if len(data) >= 2:
        loads = [u["load_pct"] for u in data]
        assert loads == sorted(loads, reverse=True)


def test_resource_load_with_week(client, pm_token, db):
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    res = client.get(
        f"/api/v1/dashboard/resource-load?week_start={week_start}",
        headers=auth(pm_token),
    )
    assert res.status_code == 200


def test_resource_load_requires_manager(client, dev_token, db):
    res = client.get("/api/v1/dashboard/resource-load", headers=auth(dev_token))
    assert res.status_code in (401, 403)


# ── Profitability ──────────────────────────────────────────────────────────

def test_profitability_admin(client, admin_token, db):
    res = client.get("/api/v1/dashboard/profitability", headers=auth(admin_token))
    assert res.status_code == 200
    data = res.json()["data"]
    assert isinstance(data, list)


def test_profitability_structure(client, admin_token, pm_token, db):
    make_project(client, pm_token, code="PROF1")
    res = client.get("/api/v1/dashboard/profitability", headers=auth(admin_token))
    data = res.json()["data"]
    if data:
        p = data[0]
        assert "project_id" in p
        assert "total_cost" in p
        assert "total_hours" in p


def test_profitability_requires_admin(client, pm_token, db):
    res = client.get("/api/v1/dashboard/profitability", headers=auth(pm_token))
    assert res.status_code in (401, 403)


def test_profitability_with_date_filter(client, admin_token, db):
    today = date.today()
    res = client.get(
        f"/api/v1/dashboard/profitability?date_from={today - timedelta(days=30)}&date_to={today}",
        headers=auth(admin_token),
    )
    assert res.status_code == 200


def test_profitability_avoids_n_plus_one_queries(client, admin_token, pm_token, db):
    db.add_all([
        Project(
            id="profit-q1",
            code="PROFQ1",
            name="Profit Query 1",
            project_type=ProjectType.consulting,
            status=ProjectStatus.active,
            is_billable=True,
            billing_rate=100,
            pm_id="pm-test-id",
            created_by="admin-test-id",
        ),
        Project(
            id="profit-q2",
            code="PROFQ2",
            name="Profit Query 2",
            project_type=ProjectType.consulting,
            status=ProjectStatus.active,
            is_billable=True,
            billing_rate=100,
            pm_id="pm-test-id",
            created_by="admin-test-id",
        ),
    ])
    db.flush()
    db.add_all([
        Imputation(user_id="dev-test-id", project_id="profit-q1", date=date.today(), hours=4, cost_amount=200),
        Imputation(user_id="dev-test-id", project_id="profit-q2", date=date.today(), hours=3, cost_amount=150),
    ])
    db.commit()

    db.query(User).filter(User.id == "admin-test-id").first()
    select_count = 0

    def _before_cursor_execute(_conn, _cursor, statement, _parameters, _context, _executemany):
        nonlocal select_count
        if statement.lstrip().upper().startswith("SELECT"):
            select_count += 1

    event.listen(db.bind, "before_cursor_execute", _before_cursor_execute)
    try:
        data = get_profitability(None, None, db=db)
    finally:
        event.remove(db.bind, "before_cursor_execute", _before_cursor_execute)

    assert len(data) >= 2
    # 3 constant queries (NOT N+1): (1) projects, (2) Project.phases selectin batch
    # — lazy="selectin" fires ONE batched query for all projects regardless of count
    # (see app/models/project.py:102) — and (3) the imputation cost/hours aggregate.
    # None of these scale with the number of projects/imputations, so this is not a
    # regression; the threshold was bumped from 2 to 3 to account for the phases
    # selectin load that prevents N+1 in the project serializers.
    assert select_count <= 3


# ── Team Productivity ──────────────────────────────────────────────────────

def test_team_productivity(client, pm_token, db):
    res = client.get("/api/v1/dashboard/productivity/team", headers=auth(pm_token))
    assert res.status_code == 200
    data = res.json()["data"]
    assert "period_start" in data
    assert "period_end" in data
    assert "team_stats" in data
    assert isinstance(data["team_stats"], list)


def test_team_productivity_with_dates(client, pm_token, db):
    today = date.today()
    res = client.get(
        f"/api/v1/dashboard/productivity/team?date_from={today - timedelta(days=7)}&date_to={today}",
        headers=auth(pm_token),
    )
    assert res.status_code == 200


def test_team_productivity_requires_manager(client, dev_token, db):
    res = client.get("/api/v1/dashboard/productivity/team", headers=auth(dev_token))
    assert res.status_code in (401, 403)
