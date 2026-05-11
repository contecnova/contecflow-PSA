"""Regression tests for public forms soft-delete behavior."""

from tests.conftest import auth
from app.models.public_forms import PublicForm


def test_delete_public_form_is_soft_and_hidden(client, pm_token, db):
    created = client.post(
        "/api/v1/forms",
        headers=auth(pm_token),
        json={
            "name": "Formulario QA",
            "description": "Formulario para validar borrado",
            "form_type": "ticket",
            "is_active": True,
            "default_priority": "medium",
            "notify_emails": [],
        },
    )
    assert created.status_code in (200, 201)
    payload = created.json()
    form_id = payload["id"]
    token = payload["token"]

    deleted = client.delete(f"/api/v1/forms/{form_id}", headers=auth(pm_token))
    assert deleted.status_code == 200
    assert deleted.json().get("ok") is True

    listed = client.get("/api/v1/forms", headers=auth(pm_token))
    assert listed.status_code == 200
    ids = [item["id"] for item in listed.json()]
    assert form_id not in ids

    fetched = client.get(f"/api/v1/forms/{form_id}", headers=auth(pm_token))
    assert fetched.status_code == 404

    public_meta = client.get(f"/api/v1/forms/public/{token}")
    assert public_meta.status_code == 404

    row = db.query(PublicForm).filter(PublicForm.id == form_id).first()
    assert row is not None
    assert row.is_active is False
