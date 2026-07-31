"""tests/test_bi_anomaly.py — Tests for BI Anomaly Detection + Churn Prediction endpoints."""
import pytest
from tests.conftest import auth


def test_anomaly_info(client, admin_token):
    r = client.get("/api/v1/bi/anomaly/info", headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert "sklearn_available" in data


def test_detect_anomalies_default(client, admin_token):
    payload = {"metric": "revenue", "contamination": 0.1}
    r = client.post("/api/v1/bi/anomaly/detect", json=payload, headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert "anomalies" in data
    assert "total_points" in data


def test_detect_anomalies_with_data(client, admin_token):
    payload = {
        "metric": "tickets",
        "data_points": [10, 12, 11, 55, 10, 9, 11],
        "contamination": 0.15,
    }
    r = client.post("/api/v1/bi/anomaly/detect", json=payload, headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert "anomalies" in data
    assert "anomaly_indices" in data


def test_churn_predict_info(client, admin_token):
    payload = {
        "client_id": "client-abc",
        "features": {
            "monthly_revenue": 5000,
            "support_tickets_last_90d": 2,
            "nps_score": 7,
            "contract_months_remaining": 6,
            "logins_last_30d": 15,
            "open_invoices": 0,
        }
    }
    r = client.post("/api/v1/bi/churn/predict", json=payload, headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert "client_id" in data
    assert "churn_probability" in data
    assert 0.0 <= data["churn_probability"] <= 1.0
    assert "risk_level" in data


def test_churn_predict_batch_contract(client, admin_token):
    payload = {
        "clients": [
            {
                "client_id": "c-1",
                "client_name": "ACME",
                "tickets_last_30d": 14,
                "response_time_avg_h": 10,
                "nps_score": 4,
                "contract_renewal_days": 20,
                "support_escalations": 3,
                "last_login_days_ago": 45,
                "active_projects": 1,
            }
        ]
    }
    r = client.post("/api/v1/bi/churn/predict", json=payload, headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert "clients" in data
    assert data["total_clients"] == 1
    assert data["method_used"] in ("lightgbm", "lightgbm_synthetic", "rule_based")


def test_anomaly_requires_auth(client):
    r = client.post("/api/v1/bi/anomaly/detect", json={"metric": "revenue"})
    assert r.status_code == 401
