"""Tareas de cumplimiento del catalogo: nacen al pedir (o aprobar) y cierran la peticion."""
from __future__ import annotations

import pytest

from tests.conftest import auth


@pytest.fixture()
def servicio(db):
    from app.models.service_desk import AgentGroup, ServiceCategory, SupportLevel
    for gid, nombre in (("cola-sis", "Sistemas"), ("cola-log", "Logística")):
        db.add(AgentGroup(id=gid, name=nombre, support_level=SupportLevel.l1, organization_id="1"))
    c = ServiceCategory(name="Altas", organization_id="1")
    db.add(c)
    db.commit()
    return c


def _crear_servicio(client, token, cat, **extra):
    r = client.post("/api/v1/sd/catalog/services", headers=auth(token), json={
        "category_id": cat.id, "name": "Alta de empleado", **extra,
        "fulfillment_tasks": [{"title": "Crear la cuenta", "group_id": "cola-sis"},
                              {"title": "Entregar el portátil", "group_id": "cola-log"}]})
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def _pedir(client, token, sid):
    r = client.post("/api/v1/sd/tickets", headers=auth(token), json={
        "title": "Alta de Marta", "description": "Empieza el lunes", "ticket_type": "service_request",
        "service_item_id": sid, "urgency": "medium", "impact": "user"})
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def test_una_tarea_con_cola_inexistente_no_se_guarda(client, admin_token, servicio):
    r = client.post("/api/v1/sd/catalog/services", headers=auth(admin_token), json={
        "category_id": servicio.id, "name": "X", "fulfillment_tasks": [{"title": "T", "group_id": "no-existe"}]})
    assert r.status_code == 422


def test_al_pedir_nacen_las_tareas_y_al_terminarlas_se_resuelve_la_peticion(client, admin_token, servicio, db):
    from app.models.service_desk import Ticket
    from app.services.service_desk.ticket_event_processor import procesar_pendientes

    pid = _pedir(client, admin_token, _crear_servicio(client, admin_token, servicio))
    detalle = client.get(f"/api/v1/sd/tickets/{pid}", headers=auth(admin_token)).json()["data"]
    tareas = detalle["fulfillment_tasks"]
    assert [(t["title"].split(" · ")[1], t["group_name"]) for t in tareas] == [("Crear la cuenta", "Sistemas"), ("Entregar el portátil", "Logística")]
    for i, t in enumerate(tareas):
        client.patch(f"/api/v1/sd/tickets/{t['id']}", headers=auth(admin_token), json={"status": "resolved", "resolution": "Hecho"})
        procesar_pendientes(db)
        db.expire_all()
        estado = db.get(Ticket, pid).status.value
        assert estado == ("resolved" if i == len(tareas) - 1 else estado), "solo se resuelve con la ultima"
    assert db.get(Ticket, pid).status.value == "resolved"


def test_con_aprobacion_las_tareas_nacen_al_aprobar(client, admin_token, pm_token, servicio, db):
    from app.models.service_desk import Ticket
    pid = _pedir(client, admin_token, _crear_servicio(client, admin_token, servicio,
                                                       requires_approval=True, approval_user_id="pm-test-id"))
    assert db.query(Ticket).filter(Ticket.parent_ticket_id == pid).count() == 0
    client.post(f"/api/v1/sd/tickets/{pid}/approval", headers=auth(pm_token), json={"decision": "approved"})
    assert db.query(Ticket).filter(Ticket.parent_ticket_id == pid).count() == 2
