"""Tests de OKRs — objetivos, key results, check-ins."""
from tests.conftest import auth


def test_list_objectives_empty(client, admin_token, db):
    res = client.get("/api/v1/okrs", headers=auth(admin_token))
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_create_objective(client, admin_token, db):
    res = client.post("/api/v1/okrs",
        headers=auth(admin_token),
        json={"title": "Mejorar satisfacción del cliente", "period": "Q2", "year": 2025, "status": "active"})
    assert res.status_code == 201
    data = res.json()
    assert "id" in data
    return data["id"]


def test_create_objective_requires_title(client, admin_token, db):
    res = client.post("/api/v1/okrs",
        headers=auth(admin_token),
        json={"period": "Q2", "year": 2025})
    assert res.status_code == 422


def test_add_key_result(client, admin_token, db):
    obj_id = client.post("/api/v1/okrs",
        headers=auth(admin_token),
        json={"title": "OKR con KR", "period": "Q1", "year": 2025, "status": "active"}
    ).json()["id"]
    res = client.post("/api/v1/okrs/key-results",
        headers=auth(admin_token),
        json={"objective_id": obj_id, "title": "NPS ≥ 8.0", "kr_type": "number", "target_value": 8.0})
    assert res.status_code == 201
    data = res.json()
    assert "id" in data
    assert data["progress"] == 0.0
    return data["id"]


def test_checkin_updates_progress(client, admin_token, db):
    obj_id = client.post("/api/v1/okrs",
        headers=auth(admin_token),
        json={"title": "OKR checkin test", "period": "Q3", "year": 2025, "status": "active"}
    ).json()["id"]
    kr_id = client.post("/api/v1/okrs/key-results",
        headers=auth(admin_token),
        json={"objective_id": obj_id, "title": "Revenue", "kr_type": "number", "target_value": 100}
    ).json()["id"]
    res = client.post(f"/api/v1/okrs/key-results/{kr_id}/checkin",
        headers=auth(admin_token),
        json={"value": 75, "note": "Buen progreso"})
    assert res.status_code == 201
    assert res.json()["progress"] == 75.0
    assert res.json()["current_value"] == 75


def test_checkin_full_progress(client, admin_token, db):
    obj_id = client.post("/api/v1/okrs",
        headers=auth(admin_token),
        json={"title": "OKR completo", "period": "Q4", "year": 2025, "status": "active"}
    ).json()["id"]
    kr_id = client.post("/api/v1/okrs/key-results",
        headers=auth(admin_token),
        json={"objective_id": obj_id, "title": "Meta 100%", "kr_type": "percentage", "target_value": 100}
    ).json()["id"]
    res = client.post(f"/api/v1/okrs/key-results/{kr_id}/checkin",
        headers=auth(admin_token),
        json={"value": 100})
    assert res.json()["progress"] == 100.0


def test_delete_objective_cascades_krs(client, admin_token, db):
    obj_id = client.post("/api/v1/okrs",
        headers=auth(admin_token),
        json={"title": "OKR a borrar", "period": "Q1", "year": 2026, "status": "active"}
    ).json()["id"]
    client.post("/api/v1/okrs/key-results",
        headers=auth(admin_token),
        json={"objective_id": obj_id, "title": "KR huerfano", "kr_type": "percentage", "target_value": 100})
    # Borrar el objetivo (soft delete, cascades a KRs)
    del_res = client.delete(f"/api/v1/okrs/{obj_id}", headers=auth(admin_token))
    assert del_res.status_code == 200
    data = del_res.json()
    assert data["ok"] is True
    assert data["kr_count"] == 1  # 1 KR cascaded to soft-delete
    # Verificar que no aparece en la lista (is_active filtering)
    objs = client.get("/api/v1/okrs?year=2026", headers=auth(admin_token)).json()
    assert not any(o["id"] == obj_id for o in objs)


def test_update_objective(client, admin_token, db):
    obj_id = client.post("/api/v1/okrs",
        headers=auth(admin_token),
        json={"title": "OKR original", "period": "Q1", "year": 2025, "status": "draft"}
    ).json()["id"]
    res = client.patch(f"/api/v1/okrs/{obj_id}",
        headers=auth(admin_token),
        json={"title": "OKR actualizado", "status": "active", "period": "Q1", "year": 2025})
    assert res.status_code == 200


def test_delete_key_result(client, admin_token, db):
    obj_id = client.post("/api/v1/okrs",
        headers=auth(admin_token),
        json={"title": "OKR KR delete", "period": "Q2", "year": 2026, "status": "active"}
    ).json()["id"]
    kr_id = client.post("/api/v1/okrs/key-results",
        headers=auth(admin_token),
        json={"objective_id": obj_id, "title": "KR a borrar", "kr_type": "percentage", "target_value": 50}
    ).json()["id"]
    res = client.delete(f"/api/v1/okrs/key-results/{kr_id}", headers=auth(admin_token))
    assert res.status_code == 200
    assert res.json()["ok"] is True
