"""tests/test_bi_dashboard_collab.py — Tests for BI Dashboard Collaboration endpoints."""
import pytest
from tests.conftest import auth


def test_add_comment(client, admin_token):
    payload = {
        "dashboard_id": "dash-1",
        "text": "This chart looks good! @pm_test please review",
        "widget_id": "widget-revenue",
    }
    r = client.post("/api/v1/bi/collab/comments", json=payload, headers=auth(admin_token))
    assert r.status_code in (200, 201)
    data = r.json()
    assert "id" in data
    assert data["dashboard_id"] == "dash-1"


def test_list_comments(client, admin_token):
    client.post("/api/v1/bi/collab/comments", json={"dashboard_id": "dash-list", "text": "test comment"}, headers=auth(admin_token))
    r = client.get("/api/v1/bi/collab/comments", params={"dashboard_id": "dash-list"}, headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    assert len(data["items"]) >= 1


def test_resolve_comment(client, admin_token):
    res = client.post("/api/v1/bi/collab/comments", json={"dashboard_id": "dash-x", "text": "resolve me"}, headers=auth(admin_token))
    comment_id = res.json()["id"]
    r = client.patch(f"/api/v1/bi/collab/comments/{comment_id}/resolve", headers=auth(admin_token))
    assert r.status_code == 200
    assert r.json()["resolved"] is True


def test_save_shared_view(client, admin_token):
    payload = {
        "dashboard_id": "dash-2",
        "name": "Q1 snapshot",
        "filters": {"period": "Q1-2025"},
        "is_public": False,
    }
    r = client.post("/api/v1/bi/collab/views", json=payload, headers=auth(admin_token))
    assert r.status_code in (200, 201)
    data = r.json()
    assert data["name"] == "Q1 snapshot"


def test_list_shared_views(client, admin_token):
    client.post("/api/v1/bi/collab/views", json={"dashboard_id": "dash-3", "name": "my view"}, headers=auth(admin_token))
    r = client.get("/api/v1/bi/collab/views", params={"dashboard_id": "dash-3"}, headers=auth(admin_token))
    assert r.status_code == 200
    assert "items" in r.json()


def test_toggle_reaction(client, admin_token):
    res = client.post("/api/v1/bi/collab/comments", json={"dashboard_id": "dash-4", "text": "react to me"}, headers=auth(admin_token))
    comment_id = res.json()["id"]
    r = client.post(f"/api/v1/bi/collab/comments/{comment_id}/reactions", json={"emoji": "👍"}, headers=auth(admin_token))
    assert r.status_code in (200, 201)


def test_collab_requires_auth(client):
    r = client.get("/api/v1/bi/collab/comments")
    assert r.status_code == 401
