"""Nota interna desde el panel del ticket: la ve el agente, no el cliente.

Auditoria 2026-11: el panel mandaba siempre comentarios publicos y, aunque
mandara uno interno, la ficha del agente solo devolvia los publicos.
"""
from jose import jwt

from app.core.config import settings
from app.models.client_portal import ClientUser
from app.models.service_desk import Ticket
from tests.conftest import auth


def test_la_nota_interna_la_ve_el_agente_y_no_el_portal(client, admin_token, db):
    cliente = ClientUser(full_name="Cliente", email="cliente@acme-demo.com", is_active=True)
    db.add(cliente)
    db.commit()
    tid = client.post("/api/v1/sd/tickets", headers=auth(admin_token), json={
        "title": "No arranca", "description": "x", "priority": "p3_medium", "ticket_type": "incident",
    }).json()["data"]["id"]
    db.query(Ticket).filter(Ticket.id == tid).update({"requester_client_id": cliente.id})
    db.commit()

    for cuerpo, publico in (("Lo miramos", True), ("Es el firewall", False)):
        r = client.post(f"/api/v1/sd/tickets/{tid}/comments", headers=auth(admin_token),
                        json={"body": cuerpo, "is_public": publico})
        assert r.status_code in (200, 201), r.text

    agente = client.get(f"/api/v1/sd/tickets/{tid}", headers=auth(admin_token)).json()["data"]["comments"]
    assert {(c["body"], c["is_public"]) for c in agente} >= {("Lo miramos", True), ("Es el firewall", False)}

    token = jwt.encode({"sub": cliente.id, "type": "client"}, settings.CLIENT_PORTAL_SECRET, algorithm="HS256")
    r = client.get(f"/api/v1/sd/tickets/client/{tid}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    portal = [c["body"] for c in r.json()["data"]["comments"]]
    assert "Lo miramos" in portal and "Es el firewall" not in portal
