def test_receive_realtime_notification(client, admin_token, db):
    # Simula evento
    client.post("/api/v1/events/test", json={"type": "alert", "message": "Test"}, headers={"Authorization": f"Bearer {admin_token}"})
    # Consulta centro de notificaciones
    res = client.get("/api/v1/notifications", headers={"Authorization": f"Bearer {admin_token}"})
    assert any(n["message"] == "Test" for n in res.json()["items"])
