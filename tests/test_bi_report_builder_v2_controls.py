from tests.conftest import auth


def _unwrap_data(payload):
    if isinstance(payload, dict) and "data" in payload:
        return payload["data"]
    return payload


def test_execute_controlled_returns_status_and_result(client, admin_token, db):
    res = client.post(
        "/api/v1/bi/reports/v2/presets/finance_revenue_by_client/execute-controlled",
        json={"limit": 50, "timeout_seconds": 5},
        headers=auth(admin_token),
    )
    assert res.status_code == 200, res.text
    data = _unwrap_data(res.json())
    assert "execution_id" in data
    assert "result" in data
    assert "status" in data
    assert "count" in data["result"]
    assert data["status"]["status"] in {"completed", "failed"}

    status_res = client.get(
        f"/api/v1/bi/reports/v2/executions/{data['execution_id']}",
        headers=auth(admin_token),
    )
    assert status_res.status_code == 200, status_res.text
    status_data = _unwrap_data(status_res.json())
    assert status_data["id"] == data["execution_id"]
    assert "progress" in status_data
