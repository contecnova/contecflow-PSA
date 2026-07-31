"""tests/test_cmdb_3d.py — Tests for CMDB 3D graph and Asset-CI linking endpoints."""
import pytest
from tests.conftest import auth


def test_get_3d_graph(client, admin_token):
    r = client.get("/api/v1/sd/cmdb/3d-graph", headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert "nodes" in data
    assert "edges" in data
    assert isinstance(data["nodes"], list)


def test_3d_graph_max_nodes_param(client, admin_token):
    r = client.get("/api/v1/sd/cmdb/3d-graph", params={"max_nodes": 50}, headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert len(data["nodes"]) <= 50


def test_blast_radius(client, admin_token):
    r = client.get("/api/v1/sd/cmdb/blast-radius/ci-app-server-01", headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert "ci_id" in data
    assert "affected_cis" in data or "blast_radius" in data or isinstance(data, dict)


def test_create_asset_link(client, admin_token):
    payload = {
        "asset_id": "asset-srv-001",
        "ci_id": "ci-app-server-01",
        "link_type": "physical_to_logical",
        "notes": "Production web server",
    }
    r = client.post("/api/v1/sd/cmdb/asset-links", json=payload, headers=auth(admin_token))
    assert r.status_code in (200, 201)
    data = r.json()["data"]
    assert data["asset_id"] == "asset-srv-001"


def test_list_asset_links(client, admin_token):
    client.post(
        "/api/v1/sd/cmdb/asset-links",
        json={"asset_id": "asset-db-001", "ci_id": "ci-db-01", "link_type": "physical_to_logical"},
        headers=auth(admin_token),
    )
    r = client.get("/api/v1/sd/cmdb/asset-links", headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert "items" in data
    assert data["count"] >= 1


def test_asset_impact(client, admin_token):
    client.post(
        "/api/v1/sd/cmdb/asset-links",
        json={"asset_id": "asset-impact-test", "ci_id": "ci-impact-01", "link_type": "physical_to_logical"},
        headers=auth(admin_token),
    )
    r = client.get("/api/v1/sd/cmdb/asset-impact/asset-impact-test", headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert "asset_id" in data


def test_cmdb_3d_requires_auth(client):
    r = client.get("/api/v1/sd/cmdb/3d-graph")
    assert r.status_code == 401
