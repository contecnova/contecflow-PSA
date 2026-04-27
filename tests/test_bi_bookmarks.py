"""Tests BI Bookmarks service and endpoints."""
from tests.conftest import auth


def test_list_bookmarks_empty(client, admin_token, db):
    """Listar bookmarks en org vacía devuelve lista vacía."""
    res = client.get("/api/v1/bi/bookmarks", headers=auth(admin_token))
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert isinstance(data["items"], list)


def test_create_and_get_bookmark(client, admin_token, db):
    """Crear un bookmark y recuperarlo por ID."""
    payload = {
        "name": "Vista ejecutiva Q1",
        "period_days": 90,
        "active_tab": "executive",
        "shared": False,
        "filters": {"status": "active"},
        "widget_states": {"kpi_revenue": {"expanded": True}},
    }
    create_res = client.post("/api/v1/bi/bookmarks", json=payload, headers=auth(admin_token))
    assert create_res.status_code == 201
    bm = create_res.json()
    assert bm["name"] == "Vista ejecutiva Q1"
    assert bm["period_days"] == 90
    assert bm["id"]

    get_res = client.get(f"/api/v1/bi/bookmarks/{bm['id']}", headers=auth(admin_token))
    assert get_res.status_code == 200
    assert get_res.json()["name"] == "Vista ejecutiva Q1"

    list_res = client.get("/api/v1/bi/bookmarks", headers=auth(admin_token))
    ids = [b["id"] for b in list_res.json()["items"]]
    assert bm["id"] in ids


def test_create_bookmark_missing_name_rejected(client, admin_token, db):
    """Bookmark sin nombre debe retornar 422."""
    res = client.post("/api/v1/bi/bookmarks", json={"period_days": 30}, headers=auth(admin_token))
    assert res.status_code in (422, 400)


def test_update_bookmark(client, admin_token, db):
    """Actualizar nombre y período de un bookmark."""
    create_res = client.post("/api/v1/bi/bookmarks", json={
        "name": "Original name",
        "period_days": 30,
    }, headers=auth(admin_token))
    assert create_res.status_code == 201
    bm_id = create_res.json()["id"]

    patch_res = client.patch(f"/api/v1/bi/bookmarks/{bm_id}",
                             json={"name": "Updated name", "period_days": 60},
                             headers=auth(admin_token))
    assert patch_res.status_code == 200
    assert patch_res.json()["name"] == "Updated name"
    assert patch_res.json()["period_days"] == 60


def test_delete_bookmark(client, admin_token, db):
    """Eliminar un bookmark y verificar que ya no aparece."""
    create_res = client.post("/api/v1/bi/bookmarks", json={
        "name": "To delete",
        "period_days": 7,
    }, headers=auth(admin_token))
    assert create_res.status_code == 201
    bm_id = create_res.json()["id"]

    del_res = client.delete(f"/api/v1/bi/bookmarks/{bm_id}", headers=auth(admin_token))
    assert del_res.status_code == 204

    get_res = client.get(f"/api/v1/bi/bookmarks/{bm_id}", headers=auth(admin_token))
    assert get_res.status_code == 404


def test_get_nonexistent_bookmark_returns_404(client, admin_token, db):
    """Bookmark inexistente devuelve 404."""
    res = client.get("/api/v1/bi/bookmarks/does-not-exist", headers=auth(admin_token))
    assert res.status_code == 404
