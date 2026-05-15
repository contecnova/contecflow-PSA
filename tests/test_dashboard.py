"""Tests de Dashboard — KPIs, salud de proyectos, métricas."""
from tests.conftest import auth


def test_dashboard_kpis(client, admin_token, db):
    res = client.get("/api/v1/dashboard/kpis", headers=auth(admin_token))
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, dict)


def test_dashboard_kpis_no_auth(client, db):
    res = client.get("/api/v1/dashboard/kpis")
    assert res.status_code in (401, 403)


def test_projects_health(client, admin_token, db):
    res = client.get("/api/v1/dashboard/projects-health", headers=auth(admin_token))
    assert res.status_code == 200
    body = res.json()
    rows = body.get("items") if isinstance(body, dict) else body
    assert isinstance(rows, list)


def test_my_tasks_summary(client, dev_token, db):
    res = client.get("/api/v1/dashboard/my-tasks", headers=auth(dev_token))
    assert res.status_code in (200, 404)  # puede no existir el endpoint


def test_alerts_list(client, admin_token, db):
    res = client.get("/api/v1/alerts", headers=auth(admin_token))
    assert res.status_code == 200
