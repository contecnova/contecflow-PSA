"""tests/test_bi_query_builder.py — Tests for BI self-service Query Builder endpoints."""
import pytest
from tests.conftest import auth


def test_get_schema(client, admin_token):
    r = client.get("/api/v1/bi/query-builder/schema", headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()
    assert "datasets" in data
    assert len(data["datasets"]) > 0


def test_get_schema_specific_dataset(client, admin_token):
    r = client.get("/api/v1/bi/query-builder/schema", params={"dataset": "projects"}, headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()
    assert "datasets" in data


def test_save_query(client, admin_token):
    payload = {
        "name": "Revenue by client Q1",
        "dataset": "revenue",
        "fields": ["client_name", "total_amount"],
        "filters": [{"field": "period", "op": "eq", "value": "2025-Q1"}],
        "order_by": [{"field": "total_amount", "direction": "desc"}],
        "limit": 50,
    }
    r = client.post("/api/v1/bi/query-builder/queries", json=payload, headers=auth(admin_token))
    assert r.status_code in (200, 201)
    data = r.json()
    assert "id" in data
    assert data["name"] == "Revenue by client Q1"


def test_list_queries(client, admin_token):
    client.post("/api/v1/bi/query-builder/queries", json={"name": "q1", "dataset": "projects"}, headers=auth(admin_token))
    r = client.get("/api/v1/bi/query-builder/queries", headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()
    assert "items" in data


def test_execute_query(client, admin_token):
    res = client.post("/api/v1/bi/query-builder/queries", json={"name": "exec_test", "dataset": "tickets"}, headers=auth(admin_token))
    qid = res.json()["id"]
    r = client.post(f"/api/v1/bi/query-builder/queries/{qid}/execute", headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()
    assert "rows" in data
    assert "columns" in data
    assert "row_count" in data


def test_preview_query_ad_hoc(client, admin_token):
    r = client.post(
        "/api/v1/bi/query-builder/preview",
        json={
            "dataset": "projects",
            "fields": ["name", "status"],
            "filters": [{"field": "status", "operator": "contains", "value": "active"}],
            "sort_by": "name",
            "sort_dir": "asc",
            "limit": 25,
        },
        headers=auth(admin_token),
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["dataset"] == "projects"
    assert data["columns"] == ["name", "status"]
    assert "rows" in data


def test_preview_query_group_by_and_aggregation(client, admin_token):
    r = client.post(
        "/api/v1/bi/query-builder/preview",
        json={
            "dataset": "projects",
            "fields": ["status", "budget_amount"],
            "group_by": ["status"],
            "aggregations": [{"field": "budget_amount", "func": "sum", "alias": "total_budget"}],
            "sort_by": "total_budget",
            "sort_dir": "desc",
            "limit": 50,
        },
        headers=auth(admin_token),
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["columns"] == ["status", "total_budget"]
    assert "rows" in data


def test_delete_query(client, admin_token):
    res = client.post("/api/v1/bi/query-builder/queries", json={"name": "del_test", "dataset": "timesheets"}, headers=auth(admin_token))
    qid = res.json()["id"]
    r = client.delete(f"/api/v1/bi/query-builder/queries/{qid}", headers=auth(admin_token))
    assert r.status_code in (200, 204)

    listed = client.get("/api/v1/bi/query-builder/queries", headers=auth(admin_token))
    assert listed.status_code == 200
    items = listed.json().get("items", [])
    assert all(i.get("id") != qid for i in items)


def test_query_builder_requires_auth(client):
    r = client.get("/api/v1/bi/query-builder/schema")
    assert r.status_code == 401
