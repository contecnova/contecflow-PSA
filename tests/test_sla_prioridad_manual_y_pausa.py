"""SLA: la prioridad a mano recalcula plazos y «volver al estado anterior» no pierde la pausa.

Auditoria 2026-11: solo la matriz de urgencia e impacto recalculaba los
vencimientos; y restaurar el estado previo a «pendiente» quitaba la pausa sin
sumar sus minutos, que contaban contra el SLA.
"""
from datetime import datetime, timedelta, timezone

from app.models.service_desk import Ticket
from tests.conftest import auth


def _ticket(client, token, prioridad="p4_low"):
    r = client.post("/api/v1/sd/tickets", headers=auth(token), json={
        "title": "Plazo", "description": "x", "priority": prioridad, "ticket_type": "incident"})
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]["id"]


def _due(db, tid):
    db.expire_all()
    t = db.query(Ticket).filter(Ticket.id == tid).one()
    return t.sla_response_due, t.sla_resolution_due


def test_fijar_la_prioridad_a_mano_acorta_los_plazos(client, admin_token, db):
    tid = _ticket(client, admin_token)
    resp_baja, res_baja = _due(db, tid)
    assert res_baja is not None
    r = client.patch(f"/api/v1/sd/tickets/{tid}", headers=auth(admin_token), json={"priority": "p1_critical"})
    assert r.status_code == 200, r.text
    resp_alta, res_alta = _due(db, tid)
    assert res_alta < res_baja and resp_alta < resp_baja


def test_volver_al_estado_anterior_suma_los_minutos_en_pausa(client, admin_token, db):
    tid = _ticket(client, admin_token)
    client.patch(f"/api/v1/sd/tickets/{tid}", headers=auth(admin_token), json={"status": "in_progress"})
    client.patch(f"/api/v1/sd/tickets/{tid}", headers=auth(admin_token), json={"status": "pending_client"})
    # La pausa empezo hace 90 minutos.
    db.query(Ticket).filter(Ticket.id == tid).update(
        {"sla_paused_at": datetime.now(timezone.utc) - timedelta(minutes=90), "sla_pause_minutes": 0})
    db.commit()
    r = client.post(f"/api/v1/sd/tickets/{tid}/restore-pending", headers=auth(admin_token))
    assert r.status_code == 200, r.text
    db.expire_all()
    t = db.query(Ticket).filter(Ticket.id == tid).one()
    assert t.sla_paused_at is None
    assert 89 <= (t.sla_pause_minutes or 0) <= 91
