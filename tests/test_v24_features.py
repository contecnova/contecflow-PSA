"""
tests/test_v24_features.py
Tests for the 8 new market-leader features (v24):
  1. Activity Feed
  2. @Mentions
  3. Project Health Score
  4. Recurring Tasks
  5. CPM Critical Path
  6. Resource Demand from Pipeline
  7. Vendor Scorecard
  8. What-If Simulation
"""
import pytest
from datetime import date, timedelta
from tests.conftest import auth


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _create_project(client, token, suffix="v24"):
    r = client.post("/api/v1/projects", json={
        "name": f"Test Project {suffix}",
        "project_type": "development",
        "start_date": str(date.today()),
        "end_date": str(date.today() + timedelta(days=90)),
    }, headers=auth(token))
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]["id"]


def _create_task(client, token, project_id, title="Task A", estimated_hours=8, due_offset=7):
    r = client.post("/api/v1/tasks", json={
        "project_id": project_id,
        "title": title,
        "priority": "medium",
        "estimated_hours": estimated_hours,
        "due_date": str(date.today() + timedelta(days=due_offset)),
    }, headers=auth(token))
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _create_opportunity(client, token, prob=70):
    r = client.post("/api/v1/pipeline", json={
        "name": "Big Deal v24",
        "client_name": "Acme Corp",
        "stage": "proposal",
        "probability": prob,
        "expected_revenue": 100000,
        "expected_hours": 500,
    }, headers=auth(token))
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]["id"]


def _create_vendor(client, token):
    r = client.post("/api/v1/alm/vendors", json={
        "name": "VendorTest SA",
        "category": "software",
    }, headers=auth(token))
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]["id"]


# ─── 1. Activity Feed ────────────────────────────────────────────────────────

def test_activity_empty_feed(client, admin_token, db):
    r = client.get("/api/v1/activity/activity/project/nonexistent-project", headers=auth(admin_token))
    assert r.status_code == 200
    assert r.json()["items"] == []


def test_activity_entity_feed_task(client, admin_token, pm_token, db):
    pid = _create_project(client, pm_token, "act1")
    tid = _create_task(client, pm_token, pid, "Activity Task")
    r = client.get(f"/api/v1/activity/activity/task/{tid}", headers=auth(admin_token))
    assert r.status_code == 200


def test_activity_project_feed(client, admin_token, pm_token, db):
    pid = _create_project(client, pm_token, "act2")
    _create_task(client, pm_token, pid, "Feed Task 1")
    _create_task(client, pm_token, pid, "Feed Task 2")
    r = client.get(f"/api/v1/activity/activity/project/{pid}", headers=auth(admin_token))
    assert r.status_code == 200
    assert isinstance(r.json()["items"], list)


def test_activity_pagination_params(client, admin_token, db):
    r = client.get("/api/v1/activity/activity/task/fake-id?limit=5", headers=auth(admin_token))
    assert r.status_code == 200


# ─── 2. @Mentions ────────────────────────────────────────────────────────────

def test_mentions_parse_no_mentions(client, admin_token, db):
    r = client.post("/api/v1/activity/mentions/parse", json={
        "content": "This is a comment with no mentions",
        "entity_type": "task",
        "entity_id": "fake-task-id",
    }, headers=auth(admin_token))
    assert r.status_code == 200
    assert r.json()["data"]["count"] == 0


def test_mentions_parse_nonexistent_user(client, admin_token, db):
    r = client.post("/api/v1/activity/mentions/parse", json={
        "content": "Hello @nonexistentuser123 what's up?",
        "entity_type": "task",
        "entity_id": "fake-task-id",
    }, headers=auth(admin_token))
    assert r.status_code == 200
    assert r.json()["data"]["count"] == 0


def test_mentions_my_empty(client, dev_token, db):
    r = client.get("/api/v1/activity/mentions/my", headers=auth(dev_token))
    assert r.status_code == 200
    assert isinstance(r.json()["items"], list)


def test_mentions_my_unread_filter(client, dev_token, db):
    r = client.get("/api/v1/activity/mentions/my?unread_only=true", headers=auth(dev_token))
    assert r.status_code == 200


def test_mentions_mark_read_nonexistent(client, dev_token, db):
    r = client.post("/api/v1/activity/mentions/fake-id/read", headers=auth(dev_token))
    assert r.status_code == 404


# ─── 3. Project Health Score ─────────────────────────────────────────────────

def test_health_project_not_found(client, admin_token, db):
    r = client.get("/api/v1/activity/projects/nonexistent-id/health", headers=auth(admin_token))
    assert r.status_code == 404


def test_health_current_score(client, admin_token, pm_token, db):
    pid = _create_project(client, pm_token, "health1")
    r = client.get(f"/api/v1/activity/projects/{pid}/health", headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert "current" in data
    assert "score" in data["current"]
    assert 0 <= data["current"]["score"] <= 100
    assert data["current"]["traffic_light"] in ("green", "yellow", "red")
    assert "history" in data


def test_health_compute_and_save(client, admin_token, pm_token, db):
    pid = _create_project(client, pm_token, "health2")
    r = client.post(f"/api/v1/activity/projects/{pid}/health/compute", headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert "score" in data
    assert "id" in data


def test_health_history_grows(client, admin_token, pm_token, db):
    pid = _create_project(client, pm_token, "health3")
    client.post(f"/api/v1/activity/projects/{pid}/health/compute", headers=auth(admin_token))
    client.post(f"/api/v1/activity/projects/{pid}/health/compute", headers=auth(admin_token))
    r = client.get(f"/api/v1/activity/projects/{pid}/health", headers=auth(admin_token))
    assert r.status_code == 200
    assert len(r.json()["data"]["history"]) >= 2


def test_health_portfolio(client, admin_token, pm_token, db):
    _create_project(client, pm_token, "port1")
    _create_project(client, pm_token, "port2")
    r = client.get("/api/v1/activity/projects/health/portfolio", headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()["items"]
    assert isinstance(data, list)
    if data:
        assert "score" in data[0]
        assert "traffic_light" in data[0]


def test_health_overdue_tasks_lower_score(client, admin_token, pm_token, db):
    """Tasks with past due dates (set via bulk-update) should reduce schedule_score."""
    pid = _create_project(client, pm_token, "health_overdue")
    # Create tasks and note their IDs
    task_ids = []
    for i in range(5):
        r = client.post("/api/v1/tasks", json={
            "project_id": pid,
            "title": f"Overdue Task {i}",
            "priority": "high",
        }, headers=auth(pm_token))
        task_ids.append(r.json()["id"])

    # Set due dates to the past via the bulk-dates endpoint
    past_date = str(date.today() - timedelta(days=10))
    bulk_r = client.post("/api/v1/tasks/bulk-dates", json={
        "updates": [{"id": tid, "due_date": past_date} for tid in task_ids]
    }, headers=auth(pm_token))
    # If bulk-dates not available, use individual PATCH
    if bulk_r.status_code not in (200, 204):
        for tid in task_ids:
            client.patch(f"/api/v1/tasks/{tid}", json={"due_date": past_date},
                         headers=auth(pm_token))

    r = client.get(f"/api/v1/activity/projects/{pid}/health", headers=auth(admin_token))
    assert r.status_code == 200
    # schedule_score must be below 100 when there are overdue tasks
    assert r.json()["data"]["current"]["schedule_score"] < 100


# ─── 4. Recurring Tasks ──────────────────────────────────────────────────────

def test_recurring_list_empty(client, admin_token, db):
    r = client.get("/api/v1/activity/recurring-tasks", headers=auth(admin_token))
    assert r.status_code == 200
    assert isinstance(r.json()["items"], list)


def test_recurring_create_weekly(client, admin_token, pm_token, db):
    pid = _create_project(client, pm_token, "rec1")
    r = client.post("/api/v1/activity/recurring-tasks", json={
        "project_id": pid,
        "title": "Weekly standup report",
        "freq": "weekly",
        "start_date": str(date.today()),
        "priority": "low",
    }, headers=auth(admin_token))
    assert r.status_code in (200, 201)
    assert "id" in r.json()["data"]


def test_recurring_create_daily(client, admin_token, pm_token, db):
    pid = _create_project(client, pm_token, "rec2")
    r = client.post("/api/v1/activity/recurring-tasks", json={
        "project_id": pid,
        "title": "Daily backup check",
        "freq": "daily",
        "start_date": str(date.today()),
    }, headers=auth(admin_token))
    assert r.status_code in (200, 201)


def test_recurring_invalid_freq(client, admin_token, pm_token, db):
    pid = _create_project(client, pm_token, "rec3")
    r = client.post("/api/v1/activity/recurring-tasks", json={
        "project_id": pid,
        "title": "Hourly",
        "freq": "hourly",
        "start_date": str(date.today()),
    }, headers=auth(admin_token))
    assert r.status_code == 400


def test_recurring_create_monthly_with_end(client, admin_token, pm_token, db):
    pid = _create_project(client, pm_token, "rec4")
    r = client.post("/api/v1/activity/recurring-tasks", json={
        "project_id": pid,
        "title": "Monthly review",
        "freq": "monthly",
        "start_date": str(date.today()),
        "end_date": str(date.today() + timedelta(days=365)),
    }, headers=auth(admin_token))
    assert r.status_code in (200, 201)


def test_recurring_filter_by_project(client, admin_token, pm_token, db):
    pid = _create_project(client, pm_token, "rec5")
    client.post("/api/v1/activity/recurring-tasks", json={
        "project_id": pid, "title": "Task A", "freq": "weekly",
        "start_date": str(date.today()),
    }, headers=auth(admin_token))
    r = client.get(f"/api/v1/activity/recurring-tasks?project_id={pid}", headers=auth(admin_token))
    assert r.status_code == 200
    assert len(r.json()["items"]) >= 1


def test_recurring_update(client, admin_token, pm_token, db):
    pid = _create_project(client, pm_token, "rec6")
    cr = client.post("/api/v1/activity/recurring-tasks", json={
        "project_id": pid, "title": "Old title", "freq": "weekly",
        "start_date": str(date.today()),
    }, headers=auth(admin_token))
    rt_id = cr.json()["data"]["id"]
    r = client.patch(f"/api/v1/activity/recurring-tasks/{rt_id}", json={
        "project_id": pid, "title": "New title", "freq": "daily",
        "start_date": str(date.today()),
    }, headers=auth(admin_token))
    assert r.status_code == 200


def test_recurring_delete(client, admin_token, pm_token, db):
    pid = _create_project(client, pm_token, "rec7")
    cr = client.post("/api/v1/activity/recurring-tasks", json={
        "project_id": pid, "title": "Temp", "freq": "weekly",
        "start_date": str(date.today()),
    }, headers=auth(admin_token))
    rt_id = cr.json()["data"]["id"]
    r = client.delete(f"/api/v1/activity/recurring-tasks/{rt_id}", headers=auth(admin_token))
    assert r.status_code == 200
    r2 = client.delete(f"/api/v1/activity/recurring-tasks/{rt_id}", headers=auth(admin_token))
    assert r2.status_code == 404


def test_recurring_materialize_dry_run(client, admin_token, pm_token, db):
    pid = _create_project(client, pm_token, "rec8")
    yesterday = str(date.today() - timedelta(days=1))
    client.post("/api/v1/activity/recurring-tasks", json={
        "project_id": pid, "title": "Mat Task", "freq": "daily",
        "start_date": yesterday,
    }, headers=auth(admin_token))
    r = client.post("/api/v1/activity/recurring-tasks/materialize?dry_run=true", headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["dry_run"] is True
    assert "tasks_created" in data


def test_recurring_materialize_real(client, admin_token, pm_token, db):
    pid = _create_project(client, pm_token, "rec9")
    yesterday = str(date.today() - timedelta(days=1))
    client.post("/api/v1/activity/recurring-tasks", json={
        "project_id": pid, "title": "Real Mat Task", "freq": "daily",
        "start_date": yesterday,
    }, headers=auth(admin_token))
    r = client.post("/api/v1/activity/recurring-tasks/materialize", headers=auth(admin_token))
    assert r.status_code == 200
    assert r.json()["data"]["dry_run"] is False


# ─── 5. CPM Critical Path ────────────────────────────────────────────────────

def test_cpm_no_tasks_404(client, admin_token, pm_token, db):
    pid = _create_project(client, pm_token, "cpm0")
    r = client.get(f"/api/v1/activity/projects/{pid}/critical-path", headers=auth(admin_token))
    assert r.status_code == 404


def test_cpm_single_task(client, admin_token, pm_token, db):
    pid = _create_project(client, pm_token, "cpm1")
    _create_task(client, pm_token, pid, "Only Task", estimated_hours=16)
    r = client.get(f"/api/v1/activity/projects/{pid}/critical-path", headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert "critical_path" in data
    assert "nodes" in data
    assert len(data["nodes"]) == 1
    assert data["nodes"][0]["is_critical"] is True
    assert data["project_duration_days"] > 0


def test_cpm_multiple_tasks(client, admin_token, pm_token, db):
    pid = _create_project(client, pm_token, "cpm2")
    _create_task(client, pm_token, pid, "Task X", 8)
    _create_task(client, pm_token, pid, "Task Y", 16)
    _create_task(client, pm_token, pid, "Task Z", 24)
    r = client.get(f"/api/v1/activity/projects/{pid}/critical-path", headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert len(data["nodes"]) == 3
    for node in data["nodes"]:
        assert "early_start" in node
        assert "late_finish" in node
        assert "total_float" in node
        assert "is_critical" in node


def test_cpm_fields_present(client, admin_token, pm_token, db):
    pid = _create_project(client, pm_token, "cpm3")
    _create_task(client, pm_token, pid, "CPM Task", 40)
    r = client.get(f"/api/v1/activity/projects/{pid}/critical-path", headers=auth(admin_token))
    assert r.status_code == 200
    node = r.json()["data"]["nodes"][0]
    for field in ["id", "code", "title", "duration_days", "early_start",
                  "early_finish", "late_start", "late_finish", "total_float", "is_critical"]:
        assert field in node, f"Missing field: {field}"


# ─── 6. Resource Demand from Pipeline ────────────────────────────────────────

def test_demand_empty(client, admin_token, db):
    r = client.get("/api/v1/activity/pipeline/resource-demand", headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert "demand_by_role" in data
    assert "opportunities_in_scope" in data


def test_demand_add_line(client, admin_token, pm_token, db):
    opp_id = _create_opportunity(client, pm_token)
    r = client.post("/api/v1/activity/pipeline/resource-demand-lines", json={
        "opportunity_id": opp_id,
        "role_or_skill": "Backend Developer",
        "hours_required": 320,
        "start_date": str(date.today() + timedelta(days=30)),
        "end_date": str(date.today() + timedelta(days=120)),
    }, headers=auth(admin_token))
    assert r.status_code in (200, 201)
    assert "id" in r.json()["data"]


def test_demand_aggregates_by_role(client, admin_token, pm_token, db):
    opp_id = _create_opportunity(client, pm_token, prob=80)
    client.post("/api/v1/activity/pipeline/resource-demand-lines", json={
        "opportunity_id": opp_id, "role_or_skill": "DevOps Engineer", "hours_required": 160,
    }, headers=auth(admin_token))
    client.post("/api/v1/activity/pipeline/resource-demand-lines", json={
        "opportunity_id": opp_id, "role_or_skill": "DevOps Engineer", "hours_required": 80,
    }, headers=auth(admin_token))
    r = client.get("/api/v1/activity/pipeline/resource-demand", headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    roles = {item["role"] for item in data["demand_by_role"]}
    assert "DevOps Engineer" in roles
    devops = next(x for x in data["demand_by_role"] if x["role"] == "DevOps Engineer")
    assert devops["total_hours"] >= 240


def test_demand_weighted_hours(client, admin_token, pm_token, db):
    opp_id = _create_opportunity(client, pm_token, prob=50)
    client.post("/api/v1/activity/pipeline/resource-demand-lines", json={
        "opportunity_id": opp_id, "role_or_skill": "QA Engineer", "hours_required": 100,
    }, headers=auth(admin_token))
    r = client.get("/api/v1/activity/pipeline/resource-demand?min_probability=0", headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    qa = next((x for x in data["demand_by_role"] if x["role"] == "QA Engineer"), None)
    if qa:
        assert qa["weighted_hours"] < qa["total_hours"]


def test_demand_delete_line(client, admin_token, pm_token, db):
    opp_id = _create_opportunity(client, pm_token)
    cr = client.post("/api/v1/activity/pipeline/resource-demand-lines", json={
        "opportunity_id": opp_id, "role_or_skill": "PM", "hours_required": 40,
    }, headers=auth(admin_token))
    lid = cr.json()["data"]["id"]
    r = client.delete(f"/api/v1/activity/pipeline/resource-demand-lines/{lid}", headers=auth(admin_token))
    assert r.status_code == 200


def test_demand_line_invalid_opportunity(client, admin_token, db):
    r = client.post("/api/v1/activity/pipeline/resource-demand-lines", json={
        "opportunity_id": "nonexistent-opp",
        "role_or_skill": "Developer",
        "hours_required": 100,
    }, headers=auth(admin_token))
    assert r.status_code == 404


def test_demand_min_probability_filter(client, admin_token, pm_token, db):
    _create_opportunity(client, pm_token, prob=10)
    r = client.get("/api/v1/activity/pipeline/resource-demand?min_probability=20", headers=auth(admin_token))
    assert r.status_code == 200


# ─── 7. Vendor Scorecard ─────────────────────────────────────────────────────

def test_vendor_scorecard_empty(client, admin_token, db):
    vid = _create_vendor(client, admin_token)
    r = client.get(f"/api/v1/activity/alm/vendors/{vid}/scorecard", headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["vendor_id"] == vid
    assert data["evaluations"] == []
    assert data["latest_composite"] is None


def test_vendor_add_evaluation(client, admin_token, db):
    vid = _create_vendor(client, admin_token)
    r = client.post(f"/api/v1/activity/alm/vendors/{vid}/scores", json={
        "period": "Q1-2026",
        "sla_score": 8.0,
        "quality_score": 7.5,
        "support_score": 9.0,
        "price_score": 6.0,
    }, headers=auth(admin_token))
    assert r.status_code in (200, 201)
    data = r.json()["data"]
    assert "composite_score" in data
    assert 0 < data["composite_score"] <= 10


def test_vendor_composite_all_dimensions(client, admin_token, db):
    vid = _create_vendor(client, admin_token)
    r = client.post(f"/api/v1/activity/alm/vendors/{vid}/scores", json={
        "period": "Q2-2026",
        "sla_score": 10.0,
        "quality_score": 10.0,
        "support_score": 10.0,
        "price_score": 10.0,
        "innovation_score": 10.0,
        "compliance_score": 10.0,
    }, headers=auth(admin_token))
    assert r.status_code in (200, 201)
    assert r.json()["data"]["composite_score"] == pytest.approx(10.0, abs=0.01)


def test_vendor_composite_partial_dimensions(client, admin_token, db):
    vid = _create_vendor(client, admin_token)
    r = client.post(f"/api/v1/activity/alm/vendors/{vid}/scores", json={
        "period": "Q3-2026",
        "sla_score": 6.0,
    }, headers=auth(admin_token))
    assert r.status_code in (200, 201)
    assert r.json()["data"]["composite_score"] == pytest.approx(6.0, abs=0.01)


def test_vendor_score_out_of_range(client, admin_token, db):
    vid = _create_vendor(client, admin_token)
    r = client.post(f"/api/v1/activity/alm/vendors/{vid}/scores", json={
        "period": "Q4-2026",
        "sla_score": 11.0,
    }, headers=auth(admin_token))
    assert r.status_code == 400


def test_vendor_scorecard_history_trend(client, admin_token, db):
    vid = _create_vendor(client, admin_token)
    for i, period in enumerate(["Q1-2026", "Q2-2026", "Q3-2026"]):
        client.post(f"/api/v1/activity/alm/vendors/{vid}/scores", json={
            "period": period,
            "sla_score": float(5 + i),
            "quality_score": float(6 + i),
        }, headers=auth(admin_token))
    r = client.get(f"/api/v1/activity/alm/vendors/{vid}/scorecard", headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert len(data["evaluations"]) == 3
    assert len(data["trend"]) == 3
    assert data["latest_composite"] is not None


def test_vendor_ranking(client, admin_token, db):
    vid1 = _create_vendor(client, admin_token)
    vid2 = _create_vendor(client, admin_token)
    client.post(f"/api/v1/activity/alm/vendors/{vid1}/scores", json={
        "period": "2026", "sla_score": 9.0, "quality_score": 8.0
    }, headers=auth(admin_token))
    client.post(f"/api/v1/activity/alm/vendors/{vid2}/scores", json={
        "period": "2026", "sla_score": 4.0, "quality_score": 3.0
    }, headers=auth(admin_token))
    r = client.get("/api/v1/activity/alm/vendors/scorecard/ranking", headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()["items"]
    assert len(data) >= 2
    scores = [item["composite_score"] for item in data if item["composite_score"] is not None]
    assert scores == sorted(scores, reverse=True)


def test_vendor_scorecard_rating_label(client, admin_token, db):
    vid = _create_vendor(client, admin_token)
    client.post(f"/api/v1/activity/alm/vendors/{vid}/scores", json={
        "period": "2026", "sla_score": 9.0, "quality_score": 9.0,
        "support_score": 9.0, "price_score": 9.0,
        "innovation_score": 9.0, "compliance_score": 9.0,
    }, headers=auth(admin_token))
    r = client.get(f"/api/v1/activity/alm/vendors/{vid}/scorecard", headers=auth(admin_token))
    assert r.status_code == 200
    assert r.json()["data"]["evaluations"][0]["rating"] == "Excelente"


def test_vendor_not_found(client, admin_token, db):
    r = client.get("/api/v1/activity/alm/vendors/nonexistent/scorecard", headers=auth(admin_token))
    assert r.status_code == 404


# ─── 8. What-If Simulation ───────────────────────────────────────────────────

def test_simulation_no_tasks_404(client, admin_token, pm_token, db):
    pid = _create_project(client, pm_token, "sim0")
    r = client.post(f"/api/v1/activity/projects/{pid}/simulate", json={}, headers=auth(admin_token))
    assert r.status_code == 404


def test_simulation_baseline(client, admin_token, pm_token, db):
    pid = _create_project(client, pm_token, "sim1")
    _create_task(client, pm_token, pid, "Sim Task A", 40)
    _create_task(client, pm_token, pid, "Sim Task B", 24)
    r = client.post(f"/api/v1/activity/projects/{pid}/simulate", json={}, headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert "simulation" in data
    sim = data["simulation"]
    assert sim["days_delta"] == 0
    assert "base_end_date" in sim
    assert "simulated_end_date" in sim
    assert sim["base_end_date"] == sim["simulated_end_date"]


def test_simulation_delay(client, admin_token, pm_token, db):
    pid = _create_project(client, pm_token, "sim2")
    _create_task(client, pm_token, pid, "Delay Task", 16)
    r = client.post(f"/api/v1/activity/projects/{pid}/simulate", json={"delay_days": 14}, headers=auth(admin_token))
    assert r.status_code == 200
    assert r.json()["data"]["simulation"]["days_delta"] == 14


def test_simulation_add_resources(client, admin_token, pm_token, db):
    pid = _create_project(client, pm_token, "sim3")
    _create_task(client, pm_token, pid, "Big Task", 160)
    base_r = client.post(f"/api/v1/activity/projects/{pid}/simulate", json={}, headers=auth(admin_token))
    base_delta = base_r.json()["data"]["simulation"]["days_delta"]
    boosted_r = client.post(f"/api/v1/activity/projects/{pid}/simulate", json={
        "add_resources": [{"role": "Developer", "hours_per_week": 40}],
    }, headers=auth(admin_token))
    assert boosted_r.status_code == 200
    assert boosted_r.json()["data"]["simulation"]["days_delta"] <= base_delta


def test_simulation_cut_tasks(client, admin_token, pm_token, db):
    pid = _create_project(client, pm_token, "sim4")
    _create_task(client, pm_token, pid, "Keep Task", 40)
    tid2 = _create_task(client, pm_token, pid, "Cut Task", 40)
    r = client.post(f"/api/v1/activity/projects/{pid}/simulate", json={"cut_task_ids": [tid2]}, headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["simulation"]["cut_tasks"] == 1
    assert any(t["id"] == tid2 for t in data["cut"])


def test_simulation_defer_tasks(client, admin_token, pm_token, db):
    pid = _create_project(client, pm_token, "sim5")
    _create_task(client, pm_token, pid, "Keep", 8)
    tid2 = _create_task(client, pm_token, pid, "Defer this", 40)
    r = client.post(f"/api/v1/activity/projects/{pid}/simulate", json={"defer_task_ids": [tid2]}, headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["simulation"]["deferred_tasks"] == 1
    assert any(t["id"] == tid2 for t in data["deferred"])


def test_simulation_compress_pct(client, admin_token, pm_token, db):
    pid = _create_project(client, pm_token, "sim6")
    _create_task(client, pm_token, pid, "Big", 200)
    r = client.post(f"/api/v1/activity/projects/{pid}/simulate", json={"compress_pct": 30.0}, headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert "notes" in data
    assert any("compress" in n.lower() for n in data["notes"])


def test_simulation_combined_scenario(client, admin_token, pm_token, db):
    pid = _create_project(client, pm_token, "sim7")
    _create_task(client, pm_token, pid, "Essential", 40)
    tid2 = _create_task(client, pm_token, pid, "Nice to have", 80)
    r = client.post(f"/api/v1/activity/projects/{pid}/simulate", json={
        "add_resources": [{"role": "Dev", "hours_per_week": 40, "rate_per_hour": 90}],
        "cut_task_ids": [tid2],
        "compress_pct": 20.0,
    }, headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["simulation"]["cut_tasks"] == 1
    assert "cost_delta_eur" in data["simulation"]


def test_simulation_is_read_only(client, admin_token, pm_token, db):
    """Simulation must NOT persist any changes to the DB."""
    pid = _create_project(client, pm_token, "sim8")
    tid = _create_task(client, pm_token, pid, "Unchanged Task", 40)
    client.post(f"/api/v1/activity/projects/{pid}/simulate", json={
        "cut_task_ids": [tid], "delay_days": 30,
    }, headers=auth(admin_token))
    r = client.get(f"/api/v1/tasks/{tid}", headers=auth(admin_token))
    assert r.status_code == 200
    assert r.json()["id"] == tid
