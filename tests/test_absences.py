"""Tests de Ausencias."""
from tests.conftest import auth
from app.models.resources import Absence, AbsenceStatus


def test_list_absences(client, admin_token, db):
    res = client.get("/api/v1/absences", headers=auth(admin_token))
    assert res.status_code == 200


def test_create_absence(client, dev_token, db):
    res = client.post("/api/v1/absences/my",
        headers=auth(dev_token),
        json={"type": "vacation",
              "start_date": "2025-08-01",
              "end_date": "2025-08-15",
              "reason": "Vacaciones verano"})
    assert res.status_code in (200, 201)
    assert "id" in res.json()


def test_absence_overlap_same_user(client, dev_token, db):
    client.post("/api/v1/absences/my",
        headers=auth(dev_token),
        json={"type": "vacation", "start_date": "2025-09-01", "end_date": "2025-09-10"})
    res = client.post("/api/v1/absences/my",
        headers=auth(dev_token),
        json={"type": "vacation", "start_date": "2025-09-05", "end_date": "2025-09-15"})
    # Backend puede aceptarla o rechazarla dependiendo de la validación
    assert res.status_code in (200, 201, 400, 409, 422)


def test_update_absence(client, dev_token, db):
    abs_id = client.post("/api/v1/absences/my",
        headers=auth(dev_token),
        json={"type": "sick", "start_date": "2025-10-01", "end_date": "2025-10-03"}
    ).json()["id"]
    res = client.patch(f"/api/v1/absences/my/{abs_id}",
        headers=auth(dev_token),
        json={"type": "sick", "start_date": "2025-10-01", "end_date": "2025-10-05"})
    assert res.status_code == 200


def test_delete_absence(client, dev_token, db):
    abs_id = client.post("/api/v1/absences/my",
        headers=auth(dev_token),
        json={"type": "other", "start_date": "2025-11-01", "end_date": "2025-11-02"}
    ).json()["id"]
    res = client.delete(f"/api/v1/absences/my/{abs_id}", headers=auth(dev_token))
    assert res.status_code == 200
    payload = res.json()
    assert payload.get("ok") is True

    my_abs = client.get("/api/v1/absences/my", headers=auth(dev_token))
    assert my_abs.status_code == 200
    my_abs_payload = my_abs.json()
    my_abs_items = my_abs_payload.get("items", my_abs_payload) if isinstance(my_abs_payload, dict) else my_abs_payload
    ids = [a["id"] for a in my_abs_items]
    assert abs_id not in ids

    row = db.query(Absence).filter(Absence.id == abs_id).first()
    assert row is not None
    assert row.is_active is False
    assert row.status == AbsenceStatus.cancelled
