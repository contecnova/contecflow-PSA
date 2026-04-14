"""Tests BI/Analytics — nuevas métricas, filtros, utilización avanzada, alertas de margen."""
from tests.conftest import auth


def test_filter_options_includes_types_and_clients(client, admin_token, db):
    """La respuesta de /filters/options incluye los campos nuevos."""
    res = client.get("/api/v1/analytics/filters/options", headers=auth(admin_token))
    assert res.status_code == 200
    data = res.json()
    assert "projects" in data
    assert "users" in data
    assert "departments" in data
    assert "project_types" in data
    assert "clients" in data
    assert isinstance(data["project_types"], list)
    assert isinstance(data["clients"], list)


def test_projects_by_type_metric(client, admin_token, db):
    """La métrica projects_by_type devuelve datos con type y label."""
    res = client.get("/api/v1/analytics/query/projects_by_type", headers=auth(admin_token))
    assert res.status_code == 200
    data = res.json()
    assert data["metric_id"] == "projects_by_type"
    assert "rows" in data
    assert "filters" in data
    assert "project_type" in data["filters"]
    assert "client_id" in data["filters"]
    for row in data["rows"]:
        assert "label" in row
        assert "value" in row
        assert "type" in row


def test_projects_by_type_filter_by_client(client, admin_token, db):
    """Filtrar projects_by_type por client_id devuelve 200 aunque sin datos."""
    res = client.get("/api/v1/analytics/query/projects_by_type",
                     params={"client_id": "00000000-0000-0000-0000-000000000099"},
                     headers=auth(admin_token))
    assert res.status_code == 200
    assert res.json()["rows"] == []


def test_query_hours_by_person_with_project_type_filter(client, admin_token, db):
    """Filtrar hours_by_person por project_type devuelve 200 y estructura válida."""
    res = client.get("/api/v1/analytics/query/hours_by_person",
                     params={"project_type": "consulting"},
                     headers=auth(admin_token))
    assert res.status_code == 200
    data = res.json()
    assert "rows" in data
    assert data["filters"]["project_type"] == "consulting"


def test_query_missing_metric_returns_404(client, admin_token, db):
    res = client.get("/api/v1/analytics/query/non_existent_metric_xyz", headers=auth(admin_token))
    assert res.status_code == 404


def test_advanced_utilization_endpoint(client, admin_token, db):
    """GET /analytics/utilization/advanced devuelve summary + team."""
    res = client.get("/api/v1/analytics/utilization/advanced", headers=auth(admin_token))
    assert res.status_code == 200
    data = res.json()
    assert "summary" in data
    assert "team" in data
    assert "window" in data
    s = data["summary"]
    assert "actual_utilization_pct" in s
    assert "booked_utilization_pct" in s
    assert s["capacity_hours"] >= 0


def test_advanced_utilization_project_type_filter(client, admin_token, db):
    """Filtrar utilización por project_type devuelve 200."""
    res = client.get("/api/v1/analytics/utilization/advanced",
                     params={"project_type": "development", "weeks_ahead": 2},
                     headers=auth(admin_token))
    assert res.status_code == 200
    data = res.json()
    assert data["filters"]["project_type"] == "development"


def test_advanced_utilization_team_structure(client, admin_token, db):
    """Cada miembro del equipo tiene los campos esperados."""
    res = client.get("/api/v1/analytics/utilization/advanced",
                     params={"weeks_ahead": 1},
                     headers=auth(admin_token))
    assert res.status_code == 200
    team = res.json()["team"]
    for member in team:
        assert "user_id" in member
        assert "full_name" in member
        assert "actual_utilization_pct" in member
        assert "booked_utilization_pct" in member
        assert "projected" in member
        assert len(member["projected"]) == 1  # weeks_ahead=1


def test_metric_breaches_returns_list(client, admin_token, db):
    """GET /analytics/alerts/metric-breaches devuelve estructura válida."""
    res = client.get("/api/v1/analytics/alerts/metric-breaches",
                     params={"margin_threshold_pct": 15.0},
                     headers=auth(admin_token))
    assert res.status_code == 200
    data = res.json()
    assert "threshold" in data
    assert data["threshold"] == 15.0
    assert "items" in data
    assert isinstance(data["items"], list)
    assert "total" in data
    for item in data["items"]:
        assert item["margin_pct"] < 15.0
        assert "severity" in item
        assert item["severity"] in ("critical", "warning")
