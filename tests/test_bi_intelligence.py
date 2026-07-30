"""Tests BI Intelligence — advanced analytics and orchestration endpoints."""
from tests.conftest import auth


def test_phase2_forecast_endpoint(client, admin_token):
    res = client.get(
        "/api/v1/bi/intelligence/ml/forecast/revenue",
        params={"months_ahead": 4},
        headers=auth(admin_token),
    )
    assert res.status_code == 200
    data = res.json()["data"]
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
    data = res.json()["data"]
    assert "threshold" in data
    assert "items" in data
    assert isinstance(data["items"], list)



def test_phase2_connectors_crud_and_sync(client, admin_token):
    # list
    res = client.get("/api/v1/bi/intelligence/connectors", headers=auth(admin_token))
    assert res.status_code == 200
    items = res.json()["data"].get("items", {})
    assert "salesforce" in items

    # enable connector
    res2 = client.patch(
        "/api/v1/bi/intelligence/connectors/salesforce",
        json={"enabled": True},
        headers=auth(admin_token),
    )
    assert res2.status_code == 200
    assert res2.json()["data"]["config"]["enabled"] is True

    # sync connector
    res3 = client.post("/api/v1/bi/intelligence/connectors/salesforce/sync", headers=auth(admin_token))
    assert res3.status_code == 200
    assert "status" in res3.json()["data"]



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
    assert "rows" in preview.json()["data"]

    delivery = client.get("/api/v1/bi/intelligence/delivery/overview", headers=auth(admin_token))
    assert delivery.status_code == 200
    assert "active" in delivery.json()["data"]



def test_phase2_realtime_token(client, admin_token):
    res = client.get("/api/v1/bi/intelligence/realtime/token", headers=auth(admin_token))
    assert res.status_code == 200
    data = res.json()["data"]
    assert "token" in data
    assert "stream_url" in data


def test_phase2_visual_query_builder_schema_and_preview(client, admin_token):
    schema = client.get("/api/v1/bi/intelligence/query-builder/schema", headers=auth(admin_token))
    assert schema.status_code == 200
    payload = schema.json()["data"]
    assert "entities" in payload
    assert "operators" in payload
    assert "groups" in payload
    assert "projects" in payload["entities"]

    preview = client.post(
        "/api/v1/bi/intelligence/query-builder/preview",
        json={
            "entity": "projects",
            "columns": ["code", "name", "status"],
            "filters": [{"column": "status", "operator": "contains", "value": "active"}],
            "sort": {"column": "name", "direction": "asc"},
            "limit": 25,
        },
        headers=auth(admin_token),
    )
    assert preview.status_code == 200
    data = preview.json()["data"]
    assert data["entity"] == "projects"
    assert data["columns"] == ["code", "name", "status"]
    assert "rows" in data


def test_phase2_visual_query_builder_preview_rejects_unknown_entity(client, admin_token):
    res = client.post(
        "/api/v1/bi/intelligence/query-builder/preview",
        json={"entity": "unknown_entity", "columns": ["foo"], "filters": [], "limit": 10},
        headers=auth(admin_token),
    )
    assert res.status_code == 404


def test_phase2_visual_query_builder_templates_crud(client, admin_token):
    create = client.post(
        "/api/v1/bi/intelligence/query-builder/templates",
        json={
            "name": "Proyectos activos",
            "query": {
                "entity": "projects",
                "columns": ["code", "name", "status"],
                "filters": [{"column": "status", "operator": "contains", "value": "active"}],
                "sort": {"column": "name", "direction": "asc"},
                "limit": 100,
            },
        },
        headers=auth(admin_token),
    )
    assert create.status_code == 200
    item = create.json()["data"]["item"]
    assert item["name"] == "Proyectos activos"
    template_id = item["id"]

    listed = client.get(
        "/api/v1/bi/intelligence/query-builder/templates",
        headers=auth(admin_token),
    )
    assert listed.status_code == 200
    data = listed.json()
    assert data["meta"]["total"] >= 1
    assert any(t["id"] == template_id for t in data["items"])

    deleted = client.delete(
        f"/api/v1/bi/intelligence/query-builder/templates/{template_id}",
        headers=auth(admin_token),
    )
    assert deleted.status_code == 200


def test_phase2_visual_query_builder_templates_delete_unknown_returns_404(client, admin_token):
    res = client.delete(
        "/api/v1/bi/intelligence/query-builder/templates/999999",
        headers=auth(admin_token),
    )
    assert res.status_code == 404


def test_bi_delivery_send_only_on_change_and_diff(client, admin_token, monkeypatch):
    import app.services.bi_report_builder_v2_service as rbv2
    import app.services.bi_report_delivery_service as delivery_svc

    report_state = {
        "columns": ["code", "name"],
        "rows": [{"code": "P1", "name": "Alpha"}],
    }

    send_calls = {"email": 0}

    def _fake_preview_preset(db, organization_id, preset_id, limit=5000):
        _ = (db, organization_id, preset_id, limit)
        return {"columns": report_state["columns"], "rows": report_state["rows"]}

    def _fake_send_email(recipients, subject, body_html, attachment_bytes=None, attachment_filename=None):
        _ = (recipients, subject, body_html, attachment_bytes, attachment_filename)
        send_calls["email"] += 1
        return True

    monkeypatch.setattr(rbv2, "preview_preset", _fake_preview_preset)
    monkeypatch.setattr(delivery_svc, "_send_email", _fake_send_email)

    create = client.post(
        "/api/v1/bi/delivery/schedules",
        json={
            "name": "Condicional semanal",
            "report_preset_id": "finance_revenue_by_client",
            "channels": ["email"],
            "recipients": ["ops@example.com"],
            "frequency": "daily",
            "export_format": "json",
            "send_only_on_change": True,
        },
        headers=auth(admin_token),
    )
    assert create.status_code == 201, create.text
    schedule_id = create.json()["data"]["id"]

    first = client.post(
        f"/api/v1/bi/delivery/schedules/{schedule_id}/send-now",
        headers=auth(admin_token),
    )
    assert first.status_code == 200, first.text
    first_data = first.json()["data"]
    assert first_data["skipped_no_changes"] is False
    assert first_data["diff"]["has_changes"] is True
    assert send_calls["email"] == 1

    second = client.post(
        f"/api/v1/bi/delivery/schedules/{schedule_id}/send-now",
        headers=auth(admin_token),
    )
    assert second.status_code == 200, second.text
    second_data = second.json()["data"]
    assert second_data["skipped_no_changes"] is True
    assert second_data["results"]["email"] == "skipped_no_changes"
    assert send_calls["email"] == 1

    report_state["rows"] = [
        {"code": "P1", "name": "Alpha"},
        {"code": "P2", "name": "Beta"},
    ]

    third = client.post(
        f"/api/v1/bi/delivery/schedules/{schedule_id}/send-now",
        headers=auth(admin_token),
    )
    assert third.status_code == 200, third.text
    third_data = third.json()["data"]
    assert third_data["skipped_no_changes"] is False
    assert third_data["diff"]["has_changes"] is True
    assert third_data["diff"]["added_rows"] >= 1
    assert send_calls["email"] == 2

    diff_now = client.get(
        f"/api/v1/bi/delivery/schedules/{schedule_id}/diff",
        headers=auth(admin_token),
    )
    assert diff_now.status_code == 200, diff_now.text
    assert diff_now.json()["data"]["diff"]["has_changes"] is False


def test_bi_delivery_diff_unknown_schedule_returns_404(client, admin_token):
    res = client.get(
        "/api/v1/bi/delivery/schedules/not-found/diff",
        headers=auth(admin_token),
    )
    assert res.status_code == 404


def test_bi_delivery_delete_schedule(client, admin_token):
    created = client.post(
        "/api/v1/bi/delivery/schedules",
        json={
            "name": "Delete Schedule",
            "report_preset_id": "finance_revenue_by_client",
            "channels": ["email"],
            "recipients": ["ops@example.com"],
            "frequency": "weekly",
            "export_format": "json",
            "is_active": True,
        },
        headers=auth(admin_token),
    )
    assert created.status_code == 201, created.text
    schedule_id = created.json()["data"]["id"]

    deleted = client.delete(f"/api/v1/bi/delivery/schedules/{schedule_id}", headers=auth(admin_token))
    assert deleted.status_code == 200
    assert deleted.json()["data"].get("ok") is True

    diff = client.get(f"/api/v1/bi/delivery/schedules/{schedule_id}/diff", headers=auth(admin_token))
    assert diff.status_code == 404
