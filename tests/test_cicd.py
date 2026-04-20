def test_cicd_pipeline_failure_alerts(client, admin_token, db):
    # Simula fallo en pipeline
    res = client.post("/api/v1/cicd/pipeline", json={"status": "failed", "job": "deploy"}, headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    # Verifica alerta generada
    res = client.get("/api/v1/alerts?type=cicd", headers={"Authorization": f"Bearer {admin_token}"})
    assert any(a["job"] == "deploy" and a["status"] == "failed" for a in res.json())
