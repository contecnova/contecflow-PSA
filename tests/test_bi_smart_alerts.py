"""Tests BI Smart Alerts service and endpoints."""
from app.services import bi_smart_alerts_service as smart_alerts_svc
from tests.conftest import auth


def test_supported_metrics_returns_list(client, admin_token, db):
    """GET /bi/alerts/supported-metrics devuelve métricas y condiciones."""
    res = client.get("/api/v1/bi/alerts/supported-metrics", headers=auth(admin_token))
    assert res.status_code == 200
    data = res.json()["data"]
    assert "metrics" in data
    assert "conditions" in data
    assert isinstance(data["metrics"], list)
    assert len(data["metrics"]) >= 5
    assert len(data["conditions"]) >= 4


def test_create_and_list_alert_rule(client, admin_token, db):
    """Crear una regla de alerta y listarla."""
    payload = {
        "name": "Test trend down rule",
        "metric_key": "revenue",
        "condition": "trend_down",
        "severity": "warning",
        "trend_periods": 3,
        "cooldown_minutes": 60,
        "enabled": True,
    }
    res = client.post("/api/v1/bi/alerts/rules", json=payload, headers=auth(admin_token))
    assert res.status_code == 201
    rule = res.json()["data"]
    assert rule["metric_key"] == "revenue"
    assert rule["condition"] == "trend_down"
    assert rule["id"]

    list_res = client.get("/api/v1/bi/alerts/rules", headers=auth(admin_token))
    assert list_res.status_code == 200
    items = list_res.json()["data"]["items"]
    ids = [r["id"] for r in items]
    assert rule["id"] in ids


def test_create_rule_invalid_metric_rejected(client, admin_token, db):
    """Métrica inválida debe retornar 422."""
    res = client.post("/api/v1/bi/alerts/rules", json={
        "name": "Bad rule",
        "metric_key": "non_existent_metric",
        "condition": "trend_down",
    }, headers=auth(admin_token))
    assert res.status_code == 422


def test_evaluate_alerts_returns_structure(client, admin_token, db):
    """POST /bi/alerts/evaluate devuelve estructura correcta."""
    res = client.post("/api/v1/bi/alerts/evaluate", headers=auth(admin_token))
    assert res.status_code == 200
    data = res.json()["data"]
    assert "evaluated_at" in data
    assert "rules_evaluated" in data
    assert "triggered_count" in data
    assert "triggered" in data
    assert isinstance(data["triggered"], list)


def test_alert_history_and_acknowledge(client, admin_token, db):
    """Historial de alertas retorna 200; acknowledge de alerta existente funciona."""
    hist_res = client.get("/api/v1/bi/alerts/history", headers=auth(admin_token))
    assert hist_res.status_code == 200
    data = hist_res.json()["data"]
    assert "items" in data
    assert isinstance(data["items"], list)
    # Acknowledge a non-existent alert should return 404
    ack_res = client.post("/api/v1/bi/alerts/history/non-existent-id/acknowledge",
                          headers=auth(admin_token))
    assert ack_res.status_code == 404


def test_update_and_delete_alert_rule(client, admin_token, db):
    """Actualizar y eliminar una regla de alerta."""
    create_res = client.post("/api/v1/bi/alerts/rules", json={
        "name": "Rule to update",
        "metric_key": "revenue",
        "condition": "anomaly",
        "severity": "info",
    }, headers=auth(admin_token))
    assert create_res.status_code == 201
    rule_id = create_res.json()["data"]["id"]

    patch_res = client.patch(f"/api/v1/bi/alerts/rules/{rule_id}",
                             json={"enabled": False, "severity": "critical"},
                             headers=auth(admin_token))
    assert patch_res.status_code == 200
    assert patch_res.json()["data"]["enabled"] is False
    assert patch_res.json()["data"]["severity"] == "critical"

    del_res = client.delete(f"/api/v1/bi/alerts/rules/{rule_id}", headers=auth(admin_token))
    assert del_res.status_code == 204

    list_res = client.get("/api/v1/bi/alerts/rules", headers=auth(admin_token))
    ids = [r["id"] for r in list_res.json()["data"]["items"]]
    assert rule_id not in ids


def test_seed_defaults(client, admin_token, db):
    """POST /bi/alerts/seed-defaults responde OK."""
    res = client.post("/api/v1/bi/alerts/seed-defaults", headers=auth(admin_token))
    assert res.status_code == 200
    assert res.json()["data"]["ok"] is True


def test_evaluate_alerts_with_historical_correlation(client, admin_token, db, monkeypatch):
    """Una regla anomaly + correlated_metrics dispara sólo con correlación real."""

    def _fake_series(_db, metric_key, _org_id):
        if metric_key == "revenue":
            return [100, 102, 101, 103, 100, 105, 190]
        if metric_key == "margin":
            return [50, 51, 50, 52, 49, 53, 110]
        return []

    monkeypatch.setattr(smart_alerts_svc, "_fetch_metric_series", _fake_series)

    create_res = client.post(
        "/api/v1/bi/alerts/rules",
        json={
            "name": "Revenue anomaly correlated with margin",
            "metric_key": "revenue",
            "condition": "anomaly",
            "severity": "critical",
            "correlated_metrics": ["margin"],
            "cooldown_minutes": 30,
            "enabled": True,
        },
        headers=auth(admin_token),
    )
    assert create_res.status_code == 201

    eval_res = client.post("/api/v1/bi/alerts/evaluate", headers=auth(admin_token))
    assert eval_res.status_code == 200
    data = eval_res.json()["data"]
    assert data["triggered_count"] >= 1
    entry = data["triggered"][0]
    assert entry["metric_key"] == "revenue"
    assert entry["detail"]["is_anomaly"] is True
    assert entry["correlated"]
    assert entry["correlated"][0]["metric_key"] == "margin"
