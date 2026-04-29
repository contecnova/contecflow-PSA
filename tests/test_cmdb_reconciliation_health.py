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


def test_cmdb_reconciliation_candidates_endpoint(client, admin_token, monkeypatch):
    import app.api.v1.endpoints.service_desk.cmdb as cmdb_ep

    captured = {}

    def _fake_candidates(db, provider_type=None, min_confidence=0.85):
        captured["provider_type"] = provider_type
        captured["min_confidence"] = min_confidence
        return [
            {
                "provider": "aws",
                "confidence": 0.91,
                "keeper": {"id": "ci-1", "name": "api-01", "hostname": "api-01", "ip_address": "10.0.0.1"},
                "duplicate": {"id": "ci-2", "name": "api01", "hostname": "api01", "ip_address": "10.0.0.1"},
            }
        ]

    monkeypatch.setattr(cmdb_ep, "deduplicate_candidates", _fake_candidates)

    res = client.get(
        "/api/v1/sd/cmdb/discovery/reconciliation-candidates?provider_type=aws&min_confidence=0.9",
        headers=auth(admin_token),
    )
    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["count"] == 1
    assert payload["min_confidence"] == 0.9
    assert payload["items"][0]["confidence"] == 0.91
    assert captured["provider_type"] == "aws"
    assert captured["min_confidence"] == 0.9


def test_cmdb_reconciliation_merge_endpoint(client, admin_token, monkeypatch):
    import app.api.v1.endpoints.service_desk.cmdb as cmdb_ep

    captured = {}

    def _fake_merge(db, provider_type=None, min_confidence=0.9, limit=100):
        captured["provider_type"] = provider_type
        captured["min_confidence"] = min_confidence
        captured["limit"] = limit
        return {
            "provider_filter": provider_type,
            "min_confidence": min_confidence,
            "candidates": 2,
            "merged": 1,
            "applied": [{"keeper": {"id": "ci-1"}, "duplicate": {"id": "ci-2"}, "confidence": 0.95}],
        }

    monkeypatch.setattr(cmdb_ep, "auto_merge_duplicates", _fake_merge)

    res = client.post(
        "/api/v1/sd/cmdb/discovery/reconciliation-merge?provider_type=aws&min_confidence=0.92&limit=10",
        headers=auth(admin_token),
    )
    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["ok"] is True
    assert payload["merged"] == 1
    assert payload["candidates"] == 2
    assert captured["provider_type"] == "aws"
    assert captured["min_confidence"] == 0.92
    assert captured["limit"] == 10
