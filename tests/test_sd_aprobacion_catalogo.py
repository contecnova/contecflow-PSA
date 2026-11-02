"""Aprobacion del catalogo y catalogo protegido.

Auditoria 2026-11: `requires_approval` y `approval_user_id` se guardaban y
nadie los comprobaba. Y `GET /sd/catalog` respondia sin login con el catalogo
interno de todas las organizaciones (medido con un cliente sin cookies).
"""
from __future__ import annotations

import pytest

from tests.conftest import auth


@pytest.fixture()
def servicio(db):
    from app.models.service_desk import ServiceCategory, ServiceItem

    c = ServiceCategory(name="Accesos", organization_id="1")
    db.add(c)
    db.flush()
    s = ServiceItem(category_id=c.id, name="Acceso a nómina", requires_approval=True,
                    approval_user_id="pm-test-id", organization_id="1")
    db.add(s)
    db.commit()
    return s


def _crear(client, token, servicio):
    r = client.post("/api/v1/sd/tickets", headers=auth(token), json={
        "title": "Necesito acceso a nómina", "description": "Para el cierre", "ticket_type": "service_request",
        "service_item_id": servicio.id, "urgency": "medium", "impact": "user"})
    assert r.status_code == 200, r.text
    return r.json()["data"]


def test_un_servicio_con_aprobacion_deja_el_ticket_pendiente_y_avisa_al_aprobador(client, admin_token, db, servicio):
    from app.models.service_desk import TicketApproval, TicketEvent

    t = _crear(client, admin_token, servicio)
    assert t["approval_status"] == "pending"
    a = db.query(TicketApproval).one()
    assert (a.approver_user_id, a.status) == ("pm-test-id", "pending")
    ev = db.query(TicketEvent).filter(TicketEvent.kind == "approval_requested").one()
    assert "pm-test-id" in ev.data


def test_pendiente_no_se_puede_empezar_ni_resolver(client, admin_token, servicio):
    t = _crear(client, admin_token, servicio)
    for estado in ("in_progress", "resolved"):
        r = client.patch(f"/api/v1/sd/tickets/{t['id']}", headers=auth(admin_token), json={"status": estado})
        assert r.status_code == 409, (estado, r.text)


def test_el_aprobador_aprueba_y_el_ticket_se_puede_trabajar(client, admin_token, pm_token, servicio):
    t = _crear(client, admin_token, servicio)
    mias = client.get("/api/v1/sd/approvals/mine", headers=auth(pm_token)).json()["items"]
    assert [m["ticket_id"] for m in mias] == [t["id"]]
    r = client.post(f"/api/v1/sd/tickets/{t['id']}/approval", headers=auth(pm_token), json={"decision": "approved"})
    assert r.status_code == 200, r.text
    detalle = client.get(f"/api/v1/sd/tickets/{t['id']}", headers=auth(admin_token)).json()["data"]
    assert detalle["approval_status"] == "approved" and detalle["approval"]["decided_by_name"] == "PM Test"
    assert client.patch(f"/api/v1/sd/tickets/{t['id']}", headers=auth(admin_token),
                        json={"status": "in_progress"}).status_code == 200


def test_rechazar_pide_motivo_y_cancela_el_ticket(client, admin_token, pm_token, servicio):
    t = _crear(client, admin_token, servicio)
    url = f"/api/v1/sd/tickets/{t['id']}/approval"
    assert client.post(url, headers=auth(pm_token), json={"decision": "rejected"}).status_code == 422
    assert client.post(url, headers=auth(pm_token),
                       json={"decision": "rejected", "comment": "Sin justificación"}).status_code == 200
    d = client.get(f"/api/v1/sd/tickets/{t['id']}", headers=auth(admin_token)).json()["data"]
    assert (d["status"], d["approval_status"], d["resolution"]) == ("cancelled", "rejected", "Sin justificación")


def test_un_aprobador_empleado_ve_y_decide_y_otro_empleado_no(client, admin_token, servicio, db):
    from app.core.security import create_access_token
    from app.models.user import User, UserRole, UserStatus

    for uid in ("jefe-empleado", "otro-agente"):
        db.add(User(id=uid, username=uid, email=f"{uid}@x.com", full_name=uid, role=UserRole.employee,
                    status=UserStatus.active, is_active=True, hashed_password="x", organization_id="1"))
    servicio.approval_user_id = "jefe-empleado"
    db.commit()
    t = _crear(client, admin_token, servicio)
    jefe, otro = create_access_token("jefe-empleado"), create_access_token("otro-agente")
    assert client.get(f"/api/v1/sd/tickets/{t['id']}", headers=auth(jefe)).status_code == 200
    # Quien no es el aprobador ni lo ve: 404 en vez de 403, no se revela que existe.
    assert client.post(f"/api/v1/sd/tickets/{t['id']}/approval", headers=auth(otro),
                       json={"decision": "approved"}).status_code == 404
    assert client.post(f"/api/v1/sd/tickets/{t['id']}/approval", headers=auth(jefe),
                       json={"decision": "approved"}).status_code == 200


def test_un_servicio_que_pide_aprobacion_necesita_aprobador(client, admin_token, servicio):
    r = client.post("/api/v1/sd/catalog/services", headers=auth(admin_token), json={
        "category_id": servicio.category_id, "name": "Sin aprobador", "requires_approval": True})
    assert r.status_code == 422


def test_editar_un_servicio_oculto_no_lo_publica(client, admin_token, servicio, db):
    from app.models.service_desk import ServiceItem

    servicio.is_visible_to_clients = False
    db.commit()
    lista = client.get("/api/v1/sd/catalog", headers=auth(admin_token)).json()["items"]
    s = next(s for g in lista for s in g["services"] if s["id"] == servicio.id)
    assert s["is_visible_to_clients"] is False and s["approval_user_id"] == "pm-test-id"
    client.patch(f"/api/v1/sd/catalog/services/{servicio.id}", headers=auth(admin_token), json={"name": "Renombrado"})
    db.expire_all()
    assert db.get(ServiceItem, servicio.id).is_visible_to_clients is False


def test_el_catalogo_no_se_lee_sin_login(db, servicio):
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as sin_cookies:
        assert sin_cookies.get("/api/v1/sd/catalog?public_only=false").status_code == 401


def test_un_ticket_del_correo_sin_agente_sale_en_la_cola_del_administrador(client, admin_token, pm_token, db):
    """Medido: salia en ningun listado porque no tenia usuario solicitante, agente ni creador."""
    from app.models.service_desk import Ticket

    db.add(Ticket(number="INC-0001", ticket_type="incident", title="Correo sin agente", description="d",
                  organization_id="1", requester_email="c@x.com", source="email"))
    db.add(Ticket(number="INC-0001", ticket_type="incident", title="De otra organizacion", description="d",
                  organization_id="org-otra", requester_email="c@y.com", source="email"))
    db.commit()
    for token in (admin_token, pm_token):
        titulos = [t["title"] for t in client.get("/api/v1/sd/tickets", headers=auth(token)).json()["items"]]
        assert titulos == ["Correo sin agente"]
