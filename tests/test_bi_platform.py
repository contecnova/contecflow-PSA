"""Tests BI Platform — platform scale BI capabilities."""
from tests.conftest import auth


def test_phase3_connector_catalog_and_custom_framework(client, admin_token):
    catalog = client.get("/api/v1/bi/platform/connectors/catalog", headers=auth(admin_token))
    assert catalog.status_code == 200
    payload = catalog.json()["data"]
    assert payload["count"] >= 20
    assert "salesforce" in payload["items"]

    toggle = client.patch(
        "/api/v1/bi/platform/connectors/catalog/salesforce",
        json={"enabled": True},
        headers=auth(admin_token),
    )
    assert toggle.status_code == 200
    assert toggle.json()["data"]["config"]["enabled"] is True

    create_custom = client.post(
        "/api/v1/bi/platform/connectors/custom",
        json={
            "name": "partner_api",
            "kind": "rest",
            "endpoint": "https://example.org/api/v1",
            "auth_type": "api_key",
            "enabled": True,
        },
        headers=auth(admin_token),
    )
    assert create_custom.status_code == 200
    connector = create_custom.json()["data"]["connector"]
    connector_id = connector["id"]

    listed = client.get("/api/v1/bi/platform/connectors/custom", headers=auth(admin_token))
    assert listed.status_code == 200
    assert any(x["id"] == connector_id for x in listed.json()["items"])

    tested = client.post(f"/api/v1/bi/platform/connectors/custom/{connector_id}/test", headers=auth(admin_token))
    assert tested.status_code == 200
    assert tested.json()["data"]["status"] == "ok"

    deleted = client.delete(f"/api/v1/bi/platform/connectors/custom/{connector_id}", headers=auth(admin_token))
    assert deleted.status_code == 200


def test_phase3_lineage_and_access_audit(client, admin_token):
    edge = client.post(
        "/api/v1/bi/platform/governance/lineage/edges",
        json={
            "source_table": "stg_timesheet",
            "target_table": "fact_profitability",
            "transformation_sql": "select * from stg_timesheet",
        },
        headers=auth(admin_token),
    )
    assert edge.status_code == 200
    assert edge.json()["data"]["source_table"] == "stg_timesheet"

    audit = client.post(
        "/api/v1/bi/platform/governance/audit/access",
        json={
            "entity_type": "dashboard",
            "entity_id": "executive",
            "action": "view",
            "extra": {"channel": "ui"},
        },
        headers=auth(admin_token),
    )
    assert audit.status_code == 200
    assert audit.json()["data"]["entity_type"] == "dashboard"

    lineage = client.get("/api/v1/bi/platform/governance/lineage", headers=auth(admin_token))
    assert lineage.status_code == 200
    state = lineage.json()["data"]
    assert isinstance(state.get("edges", []), list)
    assert isinstance(state.get("audit", []), list)


def test_phase3_dataset_versioning_and_diff(client, admin_token):
    s1 = client.post(
        "/api/v1/bi/platform/versioning/olap.fact_projects/snapshots",
        json={"payload": {"row_count": 10, "checksum": "a1"}},
        headers=auth(admin_token),
    )
    assert s1.status_code == 200
    id1 = s1.json()["data"]["id"]

    s2 = client.post(
        "/api/v1/bi/platform/versioning/olap.fact_projects/snapshots",
        json={"payload": {"row_count": 12, "checksum": "a2"}},
        headers=auth(admin_token),
    )
    assert s2.status_code == 200
    id2 = s2.json()["data"]["id"]

    listed = client.get("/api/v1/bi/platform/versioning/olap.fact_projects/snapshots", headers=auth(admin_token))
    assert listed.status_code == 200
    assert len(listed.json()["items"]) >= 2

    diff = client.get(
        "/api/v1/bi/platform/versioning/olap.fact_projects/diff",
        params={"from_id": id1, "to_id": id2},
        headers=auth(admin_token),
    )
    assert diff.status_code == 200
    assert diff.json()["data"]["change_count"] >= 1
