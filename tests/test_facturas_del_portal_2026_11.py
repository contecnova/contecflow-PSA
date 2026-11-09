"""Facturas en el portal del cliente (revisión 2026-11).

Medido antes: el portal enseñaba también los borradores, sin mirar
`can_view_budget`, y aprobar un borrador desde el portal lo marcaba como
enviado.
"""
from __future__ import annotations

from datetime import date

from app.models.billing_reports import Invoice
from tests.conftest import auth

CLAVE = "Clave-de-prueba-123!"


def _portal(client, pm_token, email, presupuesto=True):
    pid = client.post("/api/v1/projects", headers=auth(pm_token), json={
        "name": "Fact", "code": email[:4].upper(), "status": "active", "billing_type": "time_material"}).json()["data"]["id"]
    r = client.post("/api/v1/portal/clients", headers=auth(pm_token), json={
        "project_ids": [pid], "full_name": "Cliente", "email": email, "password": CLAVE, "can_view_budget": presupuesto})
    assert r.status_code == 200, r.text
    client.cookies.clear()
    assert client.post("/api/v1/portal/auth/login", json={"email": email, "password": CLAVE}).status_code == 200
    return pid


def _factura(db, pid, numero, estado):
    f = Invoice(number=numero, project_id=pid, organization_id="1", client_name="Cliente",
                issue_date=date(2026, 11, 1), status=estado, total=100)
    db.add(f); db.commit()
    return f


def test_EL_HALLAZGO_los_borradores_no_salen_y_aprobar_no_emite(client, db, pm_token):
    pid = _portal(client, pm_token, "fact1@cli.example")
    borrador, emitida = _factura(db, pid, "INV-B", "draft"), _factura(db, pid, "INV-E", "sent")
    ids = [i["id"] for i in client.get("/api/v1/portal/invoices").json()["items"]]
    assert emitida.id in ids and borrador.id not in ids
    assert client.post(f"/api/v1/portal/invoices/{borrador.id}/approve", json={"approved": True}).status_code == 404
    db.expire_all()
    assert str(getattr(db.get(Invoice, borrador.id).status, "value", db.get(Invoice, borrador.id).status)) == "draft"
    assert client.post(f"/api/v1/portal/invoices/{emitida.id}/approve", json={"approved": True}).status_code == 200


def test_sin_permiso_de_presupuesto_no_ve_facturas(client, db, pm_token):
    pid = _portal(client, pm_token, "fact2@cli.example", presupuesto=False)
    f = _factura(db, pid, "INV-X", "sent")
    assert client.get("/api/v1/portal/invoices").json()["items"] == []
    assert client.post(f"/api/v1/portal/invoices/{f.id}/approve", json={"approved": True}).status_code == 404
