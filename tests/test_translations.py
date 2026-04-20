def test_switch_language_and_translate(client, admin_token, db):
    # Cambia idioma
    res = client.patch("/api/v1/users/me/preferences", json={"language": "fr"}, headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    # Verifica traducción
    res = client.get("/api/v1/ui/labels?lang=fr", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    assert "Projet" in res.text or "Project" in res.text
