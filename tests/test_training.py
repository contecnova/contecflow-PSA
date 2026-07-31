"""Tests de Training & Certificaciones."""
import pytest
from app.models.training import Course
from app.models.training import CourseEnrollment
from tests.conftest import auth


def test_list_courses_empty(client, admin_token, db):
    res = client.get("/api/v1/training/courses", headers=auth(admin_token))
    assert res.status_code == 200
    payload = res.json()
    assert isinstance(payload, dict)
    assert isinstance(payload["items"], list)
    assert "meta" in payload


def test_create_course(client, admin_token, db):
    res = client.post("/api/v1/training/courses",
        headers=auth(admin_token),
        json={"title": "Python Avanzado", "provider": "Udemy",
              "category": "técnico", "duration_h": 20.0, "cost": 29.99})
    assert res.status_code == 201
    data = res.json()["data"]
    assert "id" in data


def test_employee_cannot_create_course(client, dev_token, db):
    res = client.post("/api/v1/training/courses",
        headers=auth(dev_token),
        json={"title": "Curso no autorizado"})
    assert res.status_code in (403, 401)


def test_update_course(client, admin_token, db):
    course_id = client.post("/api/v1/training/courses",
        headers=auth(admin_token),
        json={"title": "Curso original"}
    ).json()["data"]["id"]
    res = client.patch(f"/api/v1/training/courses/{course_id}",
        headers=auth(admin_token),
        json={"title": "Curso actualizado", "duration_h": 15.0})
    assert res.status_code == 200


def test_delete_course(client, admin_token, db):
    course_id = client.post("/api/v1/training/courses",
        headers=auth(admin_token),
        json={"title": "Curso a borrar"}
    ).json()["data"]["id"]
    res = client.delete(f"/api/v1/training/courses/{course_id}",
        headers=auth(admin_token))
    assert res.status_code == 200
    assert res.json()["data"]["ok"] is True

    listed = client.get("/api/v1/training/courses", headers=auth(admin_token))
    assert listed.status_code == 200
    listed_payload = listed.json()
    listed_items = listed_payload.get("items", listed_payload) if isinstance(listed_payload, dict) else listed_payload
    assert all(c["id"] != course_id for c in listed_items)

    row = db.query(Course).filter(Course.id == course_id).first()
    assert row is not None
    assert row.is_active is False


def test_list_enrollments_empty(client, admin_token, db):
    res = client.get("/api/v1/training/enrollments", headers=auth(admin_token))
    assert res.status_code == 200
    payload = res.json()
    assert isinstance(payload, dict)
    assert isinstance(payload["items"], list)
    assert "meta" in payload


def test_create_enrollment(client, admin_token, db):
    course_id = client.post("/api/v1/training/courses",
        headers=auth(admin_token),
        json={"title": "Curso inscripción"}
    ).json()["data"]["id"]
    # Obtener dev user id
    users = client.get("/api/v1/users", headers=auth(admin_token)).json()
    if isinstance(users, dict):
        users = users.get("users", users.get("items", []))
    dev = next((u for u in users if u["username"] == "dev_test"), None)
    if not dev:
        pytest.skip("dev_test no encontrado")
    res = client.post("/api/v1/training/enrollments",
        headers=auth(admin_token),
        json={"course_id": course_id, "user_id": dev["id"], "status": "planned"})
    assert res.status_code == 201


def test_delete_enrollment_hard_and_hidden(client, admin_token, db):
    course_id = client.post(
        "/api/v1/training/courses",
        headers=auth(admin_token),
        json={"title": "Curso para borrar inscripción"},
    ).json()["data"]["id"]

    users = client.get("/api/v1/users", headers=auth(admin_token)).json()
    if isinstance(users, dict):
        users = users.get("users", users.get("items", []))
    dev = next((u for u in users if u["username"] == "dev_test"), None)
    if not dev:
        pytest.skip("dev_test no encontrado")

    created = client.post(
        "/api/v1/training/enrollments",
        headers=auth(admin_token),
        json={"course_id": course_id, "user_id": dev["id"], "status": "planned"},
    ).json()["data"]

    res = client.delete(f"/api/v1/training/enrollments/{created['id']}", headers=auth(admin_token))
    assert res.status_code == 200
    assert res.json()["data"]["ok"] is True

    listed = client.get("/api/v1/training/enrollments", headers=auth(admin_token))
    assert listed.status_code == 200
    # #67: APIListResponse wrapper — items en payload["items"]
    listed_items = listed.json().get("items") if isinstance(listed.json(), dict) else listed.json()
    assert all(e["id"] != created["id"] for e in listed_items)

    row = db.query(CourseEnrollment).filter(CourseEnrollment.id == created["id"]).first()
    assert row is None


def test_add_certification(client, admin_token, db):
    users = client.get("/api/v1/users", headers=auth(admin_token)).json()
    if isinstance(users, dict):
        users = users.get("users", users.get("items", []))
    dev = next((u for u in users if u["username"] == "dev_test"), None)
    if not dev:
        pytest.skip("dev_test no encontrado")
    res = client.post("/api/v1/training/certifications",
        headers=auth(admin_token),
        json={"user_id": dev["id"], "name": "AWS Certified Developer",
              "issuer": "Amazon", "obtained_at": "2024-01-15",
              "expires_at": "2027-01-15"})
    assert res.status_code == 201


def test_expiring_certifications(client, admin_token, db):
    """Filtro de certificaciones que caducan pronto."""
    res = client.get("/api/v1/training/certifications?expiring_days=90",
        headers=auth(admin_token))
    assert res.status_code == 200
    payload = res.json()
    assert isinstance(payload, dict)
    assert isinstance(payload["items"], list)
    assert "meta" in payload
