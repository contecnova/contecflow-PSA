def test_install_and_configure_connector(client, admin_token, db):
    headers = {"Authorization": f"Bearer {admin_token}"}

    # Valid installation
    res = client.post(
        "/api/v1/integrations/instances",
        json={"connector_slug": "slack", "name": "Test Slack"},
        headers=headers,
    )
    assert res.status_code == 201
    data = res.json()
    assert data["connector"] == "slack"

    # Invalid connector slug → 404
    res = client.post(
        "/api/v1/integrations/instances",
        json={"connector_slug": "nonexistent-slug"},
        headers=headers,
    )
    assert res.status_code == 404

    # Invalid sync direction → 422
    res = client.post(
        "/api/v1/integrations/instances",
        json={"connector_slug": "slack", "sync_direction": "sideways"},
        headers=headers,
    )
    assert res.status_code == 422


def test_list_and_delete_instances(client, admin_token, db):
    headers = {"Authorization": f"Bearer {admin_token}"}

    # Install an instance
    res = client.post(
        "/api/v1/integrations/instances",
        json={"connector_slug": "github", "name": "GitHub CI"},
        headers=headers,
    )
    assert res.status_code == 201
    instance_id = res.json()["id"]

    # List includes the new instance
    res = client.get("/api/v1/integrations/instances", headers=headers)
    assert res.status_code == 200
    ids = [i["id"] for i in res.json()]
    assert instance_id in ids

    # Delete the instance
    res = client.delete(f"/api/v1/integrations/instances/{instance_id}", headers=headers)
    assert res.status_code == 204


def test_marketplace_catalog(client, admin_token, db):
    headers = {"Authorization": f"Bearer {admin_token}"}

    res = client.get("/api/v1/integrations/marketplace", headers=headers)
    assert res.status_code == 200
    connectors = res.json()
    assert len(connectors) > 0

    # Filter by category
    res = client.get("/api/v1/integrations/marketplace?category=crm", headers=headers)
    assert res.status_code == 200
    crm = res.json()
    assert all(c["category"] == "crm" for c in crm)

    # Certified only
    res = client.get("/api/v1/integrations/marketplace?certified_only=true", headers=headers)
    assert res.status_code == 200
    certified = res.json()
    assert all(c["is_certified"] for c in certified)
