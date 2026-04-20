def test_import_export_edge_cases(client, admin_token, db):
    # Importa archivo corrupto
    with open("tests/assets/corrupt_file.xlsx", "rb") as f:
        res = client.post("/api/v1/import", files={"file": ("corrupt_file.xlsx", f)}, headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 400
    # Exporta con filtros avanzados
    res = client.get("/api/v1/export?type=projects&filter=archived", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
