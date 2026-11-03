"""El filtro de estado acepta varios valores separados por comas (Kanban)."""
from app.models.service_desk import Ticket
from tests.conftest import auth


def test_varios_estados(client, admin_token, db):
    ids = []
    for estado in ("new", "in_progress", "closed"):
        r = client.post("/api/v1/sd/tickets", headers=auth(admin_token), json={
            "title": estado, "description": "x", "priority": "p3_medium", "ticket_type": "incident"})
        ids.append(r.json()["data"]["id"])
        db.query(Ticket).filter(Ticket.id == ids[-1]).update({"status": estado})
    db.commit()
    r = client.get("/api/v1/sd/tickets?status=new,in_progress&page_size=200", headers=auth(admin_token))
    assert r.status_code == 200, r.text
    vistos = {t["id"] for t in r.json()["items"]}
    assert ids[0] in vistos and ids[1] in vistos and ids[2] not in vistos
    assert r.json()["meta"]["total"] == 2
