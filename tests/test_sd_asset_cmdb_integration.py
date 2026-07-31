from tests.conftest import auth


def _create_ci(client, token, name: str, ci_type: str = "service") -> str:
    res = client.post(
        "/api/v1/sd/cmdb",
        headers=auth(token),
        json={
            "name": name,
            "ci_type": ci_type,
            "status": "operational",
            "criticality": "high",
            "owner_user_id": "admin-test-id",
        },
    )
    assert res.status_code == 200, res.text
    return res.json()["data"]["id"]


def test_asset_create_rejects_nonexistent_ci(client, admin_token):
    res = client.post(
        "/api/v1/sd/assets",
        headers=auth(admin_token),
        json={
            "name": "Laptop QA",
            "asset_type": "hardware",
            "ci_id": "non-existent-ci",
        },
    )
    assert res.status_code == 404
    assert "linked ci" in res.json().get("detail", "").lower()


def test_assets_by_ci_lists_linked_assets(client, admin_token):
    ci_id = _create_ci(client, admin_token, "Auth Service", "service")

    create_res = client.post(
        "/api/v1/sd/assets",
        headers=auth(admin_token),
        json={
            "name": "Auth API License",
            "asset_type": "software",
            "status": "deployed",
            "ci_id": ci_id,
        },
    )
    assert create_res.status_code in (200, 201), create_res.text

    res = client.get(f"/api/v1/sd/assets/by-ci/{ci_id}", headers=auth(admin_token))
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["ci_id"] == ci_id
    assert data["count"] >= 1
    assert any(a["ci_id"] == ci_id for a in data["assets"])
    assert any(a.get("ci_name") == "Auth Service" for a in data["assets"])


def test_cmdb_deprecation_impact_includes_impacted_assets(client, admin_token):
    ci_root = _create_ci(client, admin_token, "Core DB", "database")
    ci_dep = _create_ci(client, admin_token, "Billing API", "application")

    rel_res = client.post(
        "/api/v1/sd/cmdb/relations",
        headers=auth(admin_token),
        json={
            "source_ci_id": ci_dep,
            "target_ci_id": ci_root,
            "relation_type": "depends_on",
        },
    )
    assert rel_res.status_code == 200, rel_res.text

    asset_dep = client.post(
        "/api/v1/sd/assets",
        headers=auth(admin_token),
        json={
            "name": "Billing License",
            "asset_type": "software",
            "status": "deployed",
            "ci_id": ci_dep,
        },
    )
    assert asset_dep.status_code in (200, 201), asset_dep.text

    asset_root = client.post(
        "/api/v1/sd/assets",
        headers=auth(admin_token),
        json={
            "name": "DB Host",
            "asset_type": "hardware",
            "status": "deployed",
            "ci_id": ci_root,
        },
    )
    assert asset_root.status_code in (200, 201), asset_root.text

    res = client.get(
        f"/api/v1/sd/cmdb/{ci_root}/deprecation-impact?max_depth=3&include_root_assets=true",
        headers=auth(admin_token),
    )
    assert res.status_code == 200, res.text
    data = res.json()["data"]

    assert data["ci"]["id"] == ci_root
    assert "summary" in data
    assert "impacted_cis" in data
    assert "impacted_assets" in data

    impacted_ci_ids = {i["ci_id"] for i in data["impacted_cis"]}
    assert ci_dep in impacted_ci_ids

    impacted_asset_ci_ids = {a["ci_id"] for a in data["impacted_assets"]}
    assert ci_dep in impacted_asset_ci_ids
    assert ci_root in impacted_asset_ci_ids
