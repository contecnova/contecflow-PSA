def test_sync_user_preferences(client, admin_token, db):
    payload = {"language": "en", "theme_mode": "dark"}
    res = client.patch("/api/v1/users/me/preferences", json=payload, headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    # Simula login en otro dispositivo
    res2 = client.get("/api/v1/users/me/preferences", headers={"Authorization": f"Bearer {admin_token}"})
    assert res2.json()["theme_mode"] == "dark"
