"""Portal de cliente: lo que la revision del 04-11-2026 encontro roto.

Medido con un cliente real del portal sobre una copia de la base: las
solicitudes no se podian editar ni retirar, la valoracion del ticket no salia,
los botones de aprobar factura no salian, los anuncios se servian sin login,
el perfil borraba el telefono, y lo que creaba el portal o un superadmin
quedaba sin organizacion (el cliente no lo veia).
"""
from __future__ import annotations

from app.models.billing_reports import Invoice
from app.models.service_desk import Announcement, Ticket
from tests.conftest import auth

CLAVE = "ClientPass123!"


def _portal(client, pm_token, code="REV1", email="rev.portal@test.com"):
    pid = client.post("/api/v1/projects", headers=auth(pm_token), json={
        "name": "Revision", "code": code, "status": "active", "billing_type": "time_material"}).json()["data"]["id"]
    r = client.post("/api/v1/portal/clients", headers=auth(pm_token), json={
        "project_ids": [pid], "full_name": "Cliente", "email": email, "password": CLAVE,
        "can_request_changes": True, "language": "es"})
    assert r.status_code == 200, r.text
    client.cookies.clear()
    assert client.post("/api/v1/portal/auth/login", json={"email": email, "password": CLAVE}).status_code == 200
    return pid


def test_EL_HALLAZGO_la_solicitud_se_edita_y_se_retira(client, pm_token, db):
    pid = _portal(client, pm_token)
    fr = client.post("/api/v1/portal/feature-requests", json={
        "title": "Mejora", "description": "Una descripcion suficientemente larga.", "priority": "medium",
        "project_id": pid}).json()["data"]
    lista = client.get("/api/v1/portal/feature-requests").json()["items"]
    assert [x["can_edit_by_client"] for x in lista if x["id"] == fr["id"]] == [True]
    r = client.patch(f"/api/v1/portal/feature-requests/{fr['id']}", json={"title": "Mejora editada"})
    assert r.status_code == 200, r.text
    r = client.post(f"/api/v1/portal/feature-requests/{fr['id']}/withdraw")
    assert r.status_code == 200, r.text


def test_EL_HALLAZGO_el_ticket_del_portal_tiene_organizacion_y_pide_valoracion(client, pm_token, db):
    _portal(client, pm_token)
    r = client.post("/api/v1/sd/tickets/client", json={
        "title": "No va", "description": "Algo falla", "ticket_type": "incident"})
    assert r.status_code in (200, 201), r.text
    tid = r.json()["data"]["id"]
    t = db.query(Ticket).filter(Ticket.id == tid).one()
    assert t.organization_id == "1", "el ticket del portal quedaba sin organizacion"
    from datetime import datetime, timezone
    t.csat_requested_at = datetime.now(timezone.utc)
    t.status = "resolved"
    db.commit()
    detalle = client.get(f"/api/v1/sd/tickets/client/{tid}").json()["data"]
    assert detalle["csat_requested_at"], "sin este campo la pantalla no ensena las estrellas"


def test_EL_HALLAZGO_la_factura_enviada_queda_pendiente_de_aprobar_y_se_aprueba(client, pm_token, db):
    pid = _portal(client, pm_token)
    from datetime import date
    inv = Invoice(number="INV-REV-1", project_id=pid, organization_id="1", client_name="Cliente",
                  issue_date=date(2026, 11, 1), status="sent", total=100)
    db.add(inv)
    db.commit()
    fila = next(i for i in client.get("/api/v1/portal/invoices").json()["items"] if i["id"] == inv.id)
    assert fila["client_approval_status"] == "pending"
    rutas = [f"/api/v1/portal/invoices/{inv.id}/approve", f"/api/v1/portal/invoices/{inv.id}/approval"]
    r = None
    for ruta in rutas:
        r = client.post(ruta, json={"approved": True})
        if r.status_code != 404 and r.status_code != 405:
            break
    assert r.status_code == 200, r.text
    fila = next(i for i in client.get("/api/v1/portal/invoices").json()["items"] if i["id"] == inv.id)
    assert fila["client_approval_status"] == "approved"


def test_EL_HALLAZGO_los_anuncios_piden_sesion_y_el_cliente_solo_ve_los_suyos(client, pm_token, db):
    db.add(Announcement(title="Interno", body="x", show_to_clients=False, is_active=True, organization_id="1"))
    db.add(Announcement(title="Para clientes", body="y", show_to_clients=True, is_active=True, organization_id="1"))
    db.commit()
    client.cookies.clear()
    assert client.get("/api/v1/sd/announcements").status_code == 401
    _portal(client, pm_token)
    titulos = [a["title"] for a in client.get("/api/v1/sd/announcements").json()["items"]]
    assert titulos == ["Para clientes"]


def test_EL_HALLAZGO_el_perfil_trae_el_telefono(client, pm_token, db):
    _portal(client, pm_token)
    assert client.patch("/api/v1/portal/auth/me", json={"phone": "+34 600 000 000"}).status_code == 200
    assert client.get("/api/v1/portal/auth/me").json()["data"]["phone"] == "+34 600 000 000"


def test_EL_HALLAZGO_lo_que_crea_un_superadmin_hereda_la_organizacion_del_proyecto(db):
    """Su sesion no lleva organizacion: el sellado la saca del proyecto."""
    from app.db.session import _sellar_organizacion
    from app.models.project import Project, ProjectStatus, ProjectType
    from app.models.financial import ProjectMilestone
    p = Project(code="SUPA", name="S", status=ProjectStatus.active, project_type=ProjectType.development,
                organization_id="1")
    db.add(p)
    db.commit()
    db.info.pop("organization_id", None)
    hito = ProjectMilestone(project_id=p.id, name="Hito")
    db.add(hito)
    _sellar_organizacion(db)
    assert hito.organization_id == "1"
