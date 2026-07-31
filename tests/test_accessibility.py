def test_accessibility_labels_and_keyboard(client, admin_token, db):
    # Verifica etiquetas ARIA
    res = client.get("/api/v1/ui/accessibility", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    data = res.json()["data"]
    assert all("aria-label" in el for el in data["elements"])
    # Verifica navegación teclado
    res = client.get("/api/v1/ui/keyboard-nav", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    assert res.json()["data"]["tabindex"] == 0
