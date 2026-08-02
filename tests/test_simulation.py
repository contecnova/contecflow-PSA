def test_resource_demand_from_pipeline(client, admin_token, db):
    res = client.get("/api/v1/resource-demand/pipeline", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    assert "demand" in res.json()["data"]
