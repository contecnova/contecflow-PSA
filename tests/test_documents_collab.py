def test_collaborative_editing_document(client, admin_token, db):
    # Crear documento
    res = client.post("/api/v1/documents", json={"title": "Colab"}, headers={"Authorization": f"Bearer {admin_token}"})
    doc_id = res.json()["id"]
    # Simula edición colaborativa
    res = client.patch(f"/api/v1/documents/{doc_id}/edit", json={"content": "v1"}, headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    res = client.patch(f"/api/v1/documents/{doc_id}/edit", json={"content": "v2"}, headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
