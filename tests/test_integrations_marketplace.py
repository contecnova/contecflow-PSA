def test_install_and_configure_connector(client, admin_token, db):
    res = client.post("/api/v1/integrations/instances", json={"connector": "slack", "config": {"webhook_url": "https://hooks.slack.com/..."}})
    assert res.status_code == 201
    # Simula error de config
    res = client.post("/api/v1/integrations/instances", json={"connector": "slack", "config": {}})
    assert res.status_code == 400
