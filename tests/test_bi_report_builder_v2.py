"""Tests BI Report Builder v2 service and endpoints."""
from tests.conftest import auth


def test_list_presets_returns_catalog(client, admin_token, db):
    """GET /bi/reports/v2/presets devuelve al menos 15 presets."""
    res = client.get("/api/v1/bi/reports/v2/presets", headers=auth(admin_token))
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert len(data["items"]) >= 15


def test_list_presets_grouped_by_category(client, admin_token, db):
    """GET /bi/reports/v2/presets?grouped=true devuelve categorías."""
    res = client.get("/api/v1/bi/reports/v2/presets", params={"grouped": "true"},
                     headers=auth(admin_token))
    assert res.status_code == 200
    data = res.json()
    assert "categories" in data
    cats = data["categories"]
    assert "finance" in cats
    assert "delivery" in cats
    assert "executive" in cats


def test_list_categories(client, admin_token, db):
    """GET /bi/reports/v2/categories devuelve lista de categorías."""
    res = client.get("/api/v1/bi/reports/v2/categories", headers=auth(admin_token))
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert "finance" in data["items"]
    assert "executive" in data["items"]


def test_get_preset_detail(client, admin_token, db):
    """GET /bi/reports/v2/presets/{id} devuelve detalle del preset."""
    res = client.get("/api/v1/bi/reports/v2/presets/finance_revenue_by_client",
                     headers=auth(admin_token))
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == "finance_revenue_by_client"
    assert "columns" in data
    assert "sort_by" in data


def test_get_nonexistent_preset_returns_404(client, admin_token, db):
    """Preset inexistente devuelve 404."""
    res = client.get("/api/v1/bi/reports/v2/presets/does_not_exist",
                     headers=auth(admin_token))
    assert res.status_code == 404


def test_customize_preset(client, admin_token, db):
    """Personalizar un preset a nivel de org y verificar que se aplica."""
    customize_res = client.post(
        "/api/v1/bi/reports/v2/presets/finance_revenue_by_client/customize",
        json={"name": "Revenue Personalizado", "sort_direction": "asc"},
        headers=auth(admin_token),
    )
    assert customize_res.status_code == 200
    assert customize_res.json()["name"] == "Revenue Personalizado"
    assert customize_res.json()["sort_direction"] == "asc"

    # Get reflects customization
    get_res = client.get("/api/v1/bi/reports/v2/presets/finance_revenue_by_client",
                         headers=auth(admin_token))
    assert get_res.json()["name"] == "Revenue Personalizado"

    # Reset restores defaults
    reset_res = client.delete(
        "/api/v1/bi/reports/v2/presets/finance_revenue_by_client/customize",
        headers=auth(admin_token),
    )
    assert reset_res.status_code == 200
    assert reset_res.json()["name"] == "Revenue por cliente"


def test_preview_preset_returns_structure(client, admin_token, db):
    """Preview de preset devuelve estructura con columns y rows."""
    res = client.get("/api/v1/bi/reports/v2/presets/finance_revenue_by_client/preview",
                     params={"limit": 5},
                     headers=auth(admin_token))
    assert res.status_code == 200
    data = res.json()
    assert "preset_id" in data
    assert "columns" in data
    assert "rows" in data
    assert "count" in data


def test_export_preset_json(client, admin_token, db):
    """Export de preset en formato JSON devuelve filename y rows."""
    res = client.get("/api/v1/bi/reports/v2/presets/exec_top_clients/export",
                     params={"format": "json"},
                     headers=auth(admin_token))
    assert res.status_code == 200
    data = res.json()
    assert "filename" in data
    assert data["export_format"] == "json"
    assert "rows" in data
    assert data["filename"].endswith(".json")
