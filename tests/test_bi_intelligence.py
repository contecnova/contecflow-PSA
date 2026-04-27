"""Tests BI Intelligence — advanced analytics and orchestration endpoints."""
from tests.conftest import auth


def test_phase2_forecast_endpoint(client, admin_token):
    res = client.get(
        "/api/v1/bi/intelligence/ml/forecast/revenue",
        params={"months_ahead": 4},
        headers=auth(admin_token),
    )
    assert res.status_code == 200
    data = res.json()
    assert "history" in data
    assert "forecast" in data
    assert data["months_ahead"] == 4



def test_phase2_anomalies_endpoint(client, admin_token):
    res = client.get(
        "/api/v1/bi/intelligence/ml/anomalies/revenue",
        params={"z_threshold": 2.0},
        headers=auth(admin_token),
    )
    assert res.status_code == 200
    data = res.json()
    assert "threshold" in data
    assert "items" in data
    assert isinstance(data["items"], list)



def test_phase2_connectors_crud_and_sync(client, admin_token):
    # list
    res = client.get("/api/v1/bi/intelligence/connectors", headers=auth(admin_token))
    assert res.status_code == 200
    items = res.json().get("items", {})
    assert "salesforce" in items

    # enable connector
    res2 = client.patch(
        "/api/v1/bi/intelligence/connectors/salesforce",
        json={"enabled": True},
        headers=auth(admin_token),
    )
    assert res2.status_code == 200
    assert res2.json()["config"]["enabled"] is True

    # sync connector
    res3 = client.post("/api/v1/bi/intelligence/connectors/salesforce/sync", headers=auth(admin_token))
    assert res3.status_code == 200
    assert "status" in res3.json()



def test_phase2_reports_and_delivery_endpoints(client, admin_token):
    presets = client.get("/api/v1/bi/intelligence/reports/presets", headers=auth(admin_token))
    assert presets.status_code == 200
    items = presets.json().get("items", [])
    assert len(items) >= 1

    preview = client.post(
        "/api/v1/bi/intelligence/reports/preview",
        json={"preset_id": items[0]["id"], "limit": 5},
        headers=auth(admin_token),
    )
    assert preview.status_code == 200
    assert "rows" in preview.json()

    delivery = client.get("/api/v1/bi/intelligence/delivery/overview", headers=auth(admin_token))
    assert delivery.status_code == 200
    assert "active" in delivery.json()



def test_phase2_realtime_token(client, admin_token):
    res = client.get("/api/v1/bi/intelligence/realtime/token", headers=auth(admin_token))
    assert res.status_code == 200
    data = res.json()
    assert "token" in data
    assert "stream_url" in data
