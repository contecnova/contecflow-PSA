"""tests/test_bi_forecasting.py — Tests for BI Forecasting endpoints."""
from tests.conftest import auth


def test_get_supported_metrics(client, admin_token):
    r = client.get("/api/v1/bi/forecast/metrics", headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert "metrics" in data
    assert isinstance(data["metrics"], list)
    assert len(data["metrics"]) > 0


def test_forecast_linear_trend(client, admin_token):
    payload = {
        "metric": "revenue",
        "method": "linear",
        "periods": 3,
    }
    r = client.post("/api/v1/bi/forecast", json=payload, headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert "forecast" in data
    assert "method" in data
    assert len(data["forecast"]) == 3


def test_forecast_holt(client, admin_token):
    payload = {
        "metric": "tickets",
        "method": "holt",
        "periods": 5,
    }
    r = client.post("/api/v1/bi/forecast", json=payload, headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert len(data["forecast"]) == 5


def test_forecast_invalid_metric(client, admin_token):
    payload = {"metric": "nonexistent_metric_xyz", "method": "linear", "periods": 3}
    r = client.post("/api/v1/bi/forecast", json=payload, headers=auth(admin_token))
    assert r.status_code in (400, 422)


def test_multi_forecast(client, admin_token):
    payload = {
        "metrics": ["revenue", "tickets"],
        "method": "linear",
        "periods": 4,
    }
    r = client.post("/api/v1/bi/forecast/multi", json=payload, headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert "forecasts" in data
    assert len(data["forecasts"]) == 2


def test_forecast_requires_auth(client):
    payload = {"metric": "revenue", "method": "linear", "periods": 3}
    r = client.post("/api/v1/bi/forecast", json=payload)
    assert r.status_code == 401
