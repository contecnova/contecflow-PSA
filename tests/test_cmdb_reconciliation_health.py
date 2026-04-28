from tests.conftest import auth


def test_cmdb_reconciliation_health_endpoint(client, admin_token, db):
    res = client.get(
        "/api/v1/sd/cmdb/discovery/reconciliation-health",
        headers=auth(admin_token),
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert "total_discovered" in data
    assert "active_discovered" in data
    assert "stale_discovered" in data
    assert "duplicate_external_ids" in data
    assert "reconciliation_score" in data
    assert "by_provider" in data


def test_cmdb_reconciliation_health_provider_filter(client, admin_token, db):
    res = client.get(
        "/api/v1/sd/cmdb/discovery/reconciliation-health?provider_type=aws",
        headers=auth(admin_token),
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["provider_filter"] == "aws"
