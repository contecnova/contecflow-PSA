"""Tests de BPMN Processes."""

from tests.conftest import auth
from app.models.bpmn_process import BPMNProcess


def test_delete_bpmn_process_is_soft_and_hidden(client, pm_token, db):
    created = client.post(
        "/api/v1/bpmn-processes",
        headers=auth(pm_token),
        json={
            "name": "Proceso BPMN Test",
            "category": "operations",
            "description": "Proceso para test de borrado",
        },
    )
    assert created.status_code in (200, 201)
    pid = created.json()["id"]

    deleted = client.delete(f"/api/v1/bpmn-processes/{pid}", headers=auth(pm_token))
    assert deleted.status_code == 200
    payload = deleted.json()
    assert payload.get("ok") is True

    listed = client.get("/api/v1/bpmn-processes", headers=auth(pm_token))
    assert listed.status_code == 200
    ids = [p["id"] for p in listed.json()]
    assert pid not in ids

    fetched = client.get(f"/api/v1/bpmn-processes/{pid}", headers=auth(pm_token))
    assert fetched.status_code == 404

    row = db.query(BPMNProcess).filter(BPMNProcess.id == pid).first()
    assert row is not None
    assert row.is_active is False
