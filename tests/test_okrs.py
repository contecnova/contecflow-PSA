"""Tests de OKRs — objetivos, key results, check-ins."""
from app.models.okrs import KeyResult
from app.models.okrs import Objective
from tests.conftest import auth


def test_list_objectives_empty(client, admin_token, db):
    res = client.get("/api/v1/okrs", headers=auth(admin_token))
    assert res.status_code == 200
    payload = res.json()
    assert isinstance(payload, dict)
    assert isinstance(payload["items"], list)
    assert "meta" in payload


def test_create_objective(client, admin_token, db):
    res = client.post("/api/v1/okrs",
        headers=auth(admin_token),
        json={"title": "Mejorar satisfacción del cliente", "period": "Q2", "year": 2025, "status": "active"})
    assert res.status_code == 201
    data = res.json()["data"]
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
    ).json()["data"]["id"]
    res = client.post("/api/v1/okrs/key-results",
        headers=auth(admin_token),
        json={"objective_id": obj_id, "title": "NPS ≥ 8.0", "kr_type": "number", "target_value": 8.0})
    assert res.status_code == 201
    data = res.json()["data"]
    assert "id" in data
    assert data["progress"] == 0.0
    return data["id"]


def test_checkin_updates_progress(client, admin_token, db):
    obj_id = client.post("/api/v1/okrs",
        headers=auth(admin_token),
        json={"title": "OKR checkin test", "period": "Q3", "year": 2025, "status": "active"}
    ).json()["data"]["id"]
    kr_id = client.post("/api/v1/okrs/key-results",
        headers=auth(admin_token),
        json={"objective_id": obj_id, "title": "Revenue", "kr_type": "number", "target_value": 100}
    ).json()["data"]["id"]
    res = client.post(f"/api/v1/okrs/key-results/{kr_id}/checkin",
        headers=auth(admin_token),
        json={"value": 75, "note": "Buen progreso"})
    assert res.status_code == 201
    assert res.json()["data"]["progress"] == 75.0
    assert res.json()["data"]["current_value"] == 75


def test_checkin_full_progress(client, admin_token, db):
    obj_id = client.post("/api/v1/okrs",
        headers=auth(admin_token),
        json={"title": "OKR completo", "period": "Q4", "year": 2025, "status": "active"}
    ).json()["data"]["id"]
    kr_id = client.post("/api/v1/okrs/key-results",
        headers=auth(admin_token),
        json={"objective_id": obj_id, "title": "Meta 100%", "kr_type": "percentage", "target_value": 100}
    ).json()["data"]["id"]
    res = client.post(f"/api/v1/okrs/key-results/{kr_id}/checkin",
        headers=auth(admin_token),
        json={"value": 100})
    assert res.json()["data"]["progress"] == 100.0


def test_delete_objective_cascades_krs(client, admin_token, db):
    obj_id = client.post("/api/v1/okrs",
        headers=auth(admin_token),
        json={"title": "OKR a borrar", "period": "Q1", "year": 2026, "status": "active"}
    ).json()["data"]["id"]
    client.post("/api/v1/okrs/key-results",
        headers=auth(admin_token),
        json={"objective_id": obj_id, "title": "KR huerfano", "kr_type": "percentage", "target_value": 100})
    # Borrar el objetivo (soft delete, cascades a KRs)
    del_res = client.delete(f"/api/v1/okrs/{obj_id}", headers=auth(admin_token))
    assert del_res.status_code == 200
    data = del_res.json()["data"]
    assert data["ok"] is True
    assert data["kr_count"] == 1  # 1 KR cascaded to soft-delete
    # Verificar que no aparece en la lista (is_active filtering)
    objs_payload = client.get("/api/v1/okrs?year=2026", headers=auth(admin_token)).json()
    objs = objs_payload.get("items", objs_payload) if isinstance(objs_payload, dict) else objs_payload
    assert not any(o["id"] == obj_id for o in objs)

    obj_row = db.query(Objective).filter(Objective.id == obj_id).first()
    assert obj_row is not None
    assert obj_row.is_active is False

    kr_row = db.query(KeyResult).filter(KeyResult.objective_id == obj_id).first()
    assert kr_row is not None
    assert kr_row.is_active is False


def test_update_objective(client, admin_token, db):
    obj_id = client.post("/api/v1/okrs",
        headers=auth(admin_token),
        json={"title": "OKR original", "period": "Q1", "year": 2025, "status": "draft"}
    ).json()["data"]["id"]
    res = client.patch(f"/api/v1/okrs/{obj_id}",
        headers=auth(admin_token),
        json={"title": "OKR actualizado", "status": "active", "period": "Q1", "year": 2025})
    assert res.status_code == 200


def test_delete_key_result(client, admin_token, db):
    obj_id = client.post("/api/v1/okrs",
        headers=auth(admin_token),
        json={"title": "OKR KR delete", "period": "Q2", "year": 2026, "status": "active"}
    ).json()["data"]["id"]
    kr_id = client.post("/api/v1/okrs/key-results",
        headers=auth(admin_token),
        json={"objective_id": obj_id, "title": "KR a borrar", "kr_type": "percentage", "target_value": 50}
    ).json()["data"]["id"]
    res = client.delete(f"/api/v1/okrs/key-results/{kr_id}", headers=auth(admin_token))
    assert res.status_code == 200
    assert res.json()["data"]["ok"] is True


def test_objective_persists_owner_project_team(client, admin_token, db):
    """Las asignaciones (responsable, proyecto, equipo) se guardan y devuelven."""
    from app.models.user import User
    from app.models.project import Project, ProjectStatus, ProjectType
    pm = db.query(User).filter(User.username == "pm_test").first()
    # Crear un proyecto al que vincular el OKR
    p = Project(code="OKRTST", name="Proyecto OKR test", status=ProjectStatus.active,
                project_type=ProjectType.development, organization_id=pm.organization_id)
    db.add(p); db.commit()
    res = client.post(
        "/api/v1/okrs", headers=auth(admin_token),
        json={
            "title": "Reducir churn 15%",
            "description": "Bajar tasa de cancelación trimestral",
            "owner_id": pm.id,
            "project_id": p.id,
            "team_id": "Customer Success",
            "period": "Q3", "year": 2025, "status": "active",
        },
    )
    assert res.status_code == 201
    obj_id = res.json()["data"]["id"]

    # Re-leerlo y comprobar que viene serializado con todas las asignaciones
    listed_payload = client.get("/api/v1/okrs?year=2025", headers=auth(admin_token)).json()
    listed = listed_payload.get("items", listed_payload) if isinstance(listed_payload, dict) else listed_payload
    obj = next(o for o in listed if o["id"] == obj_id)
    assert obj["owner_id"] == pm.id
    assert obj["project_id"] == p.id
    assert obj["team_id"] == "Customer Success"
    # owner_name debe venir resuelto
    assert obj.get("owner_name") in (pm.full_name, pm.username)


def test_kr_persists_owner_due_date_notes(client, admin_token, db):
    """Los KR aceptan responsable, fecha límite y notas."""
    from app.models.user import User
    dev = db.query(User).filter(User.username == "dev_test").first()
    obj_id = client.post(
        "/api/v1/okrs", headers=auth(admin_token),
        json={"title": "Lanzar producto", "period": "Q2", "year": 2025, "status": "active"},
    ).json()["data"]["id"]
    res = client.post(
        "/api/v1/okrs/key-results", headers=auth(admin_token),
        json={
            "objective_id": obj_id,
            "title": "Beta privada con 50 clientes",
            "kr_type": "number", "target_value": 50,
            "owner_id": dev.id,
            "due_date": "2025-06-30",
            "notes": "Onboarding manual con cada uno",
        },
    )
    assert res.status_code == 201
    kr = res.json()["data"]
    assert kr["owner_id"] == dev.id
    assert kr["due_date"] == "2025-06-30"
    assert kr["notes"] == "Onboarding manual con cada uno"


def test_objective_accepts_null_assignments(client, admin_token, db):
    """Asignaciones opcionales: se pueden crear OKR sin owner/project/team
    (cadenas vacías → None tras la limpieza del frontend)."""
    res = client.post(
        "/api/v1/okrs", headers=auth(admin_token),
        json={
            "title": "OKR sin asignaciones",
            "owner_id": None, "project_id": None, "team_id": None,
            "period": "Q4", "year": 2025, "status": "draft",
        },
    )
    assert res.status_code == 201
