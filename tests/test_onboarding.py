def test_onboarding_progress_and_tips(client, admin_token, db):
    # Simula completar paso 1
    res = client.post("/api/v1/onboarding/step", json={"step": "profile_completed"}, headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    # Verifica tips activos
    res = client.get("/api/v1/onboarding/tips", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    assert "profile_completed" in [t["step"] for t in res.json()]
