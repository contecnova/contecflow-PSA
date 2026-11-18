def test_switch_language_and_translate(client, admin_token, db):
    # Cambia idioma
    res = client.patch("/api/v1/users/me/preferences", json={"language": "fr"}, headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    # 18-11-2026: `/ui/labels` era un relleno sin uso y se retiro; la preferencia
    # queda guardada y es la que leen el frontend y `formato_regional.idioma`.
    res = client.get("/api/v1/users/me/preferences", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    assert "fr" in res.text
