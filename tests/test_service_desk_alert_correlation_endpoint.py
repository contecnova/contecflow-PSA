from tests.conftest import auth


def test_alert_clusters_endpoint_scoped_query_no_crash(client, admin_token):
    # Regression: Ticket model has no organization_id column.
    # Endpoint must still return 200 when org scoping is requested.
    r = client.get("/api/v1/sd/alert-clusters", params={"organization_id": 1}, headers=auth(admin_token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert "clusters" in body
    assert "total" in body


def test_alert_cluster_stats_endpoint_scoped_query_no_crash(client, admin_token):
    # Same regression guard for stats endpoint.
    r = client.get("/api/v1/sd/alert-clusters/stats", params={"organization_id": 1}, headers=auth(admin_token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert "open_tickets_in_window" in body
    assert "clusters_detected" in body
