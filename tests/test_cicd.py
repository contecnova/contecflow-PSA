def test_cicd_pipeline_failure_alerts(client, admin_token, db):
    # Simula fallo en pipeline
    res = client.post("/api/v1/cicd/pipeline", json={"status": "failed", "job": "deploy"}, headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    # Verifica alerta generada en el endpoint de alertas CICD
    res = client.get("/api/v1/cicd/alerts", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    assert any(a["job"] == "deploy" and a["status"] == "failed" for a in res.json())
