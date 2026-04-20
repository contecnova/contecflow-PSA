def test_add_and_reorder_dashboard_widgets(client, admin_token, db):
    # Añadir widget
    res = client.post("/api/v1/dashboard/widgets", json={"type": "kpi", "position": 0}, headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 201
    # Reordenar widgets
    res = client.patch("/api/v1/dashboard/widgets/reorder", json={"order": [2, 1, 0]}, headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
