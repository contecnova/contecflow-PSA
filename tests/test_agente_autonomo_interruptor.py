"""Agente autonomo: interruptor por organizacion, una pasada por ticket y sus playbooks.

Auditoria 2026-11: corria cada 5 minutos en todas las organizaciones sin poder
apagarse, repetia el mismo comentario publico en cada pasada (un «assist» deja
el ticket en `new`) y no usaba los playbooks creados por la organizacion.
"""
import json

from app.models.service_desk import AutonomousPlaybook, AutonomousPlaybookExecution, Ticket, TicketComment
from app.services.service_desk.autonomous_agent_service import run_autonomous_scan
from app.services.settings_service import update_setting
from tests.conftest import auth


def _ticket(client, token):
    r = client.post("/api/v1/sd/tickets", headers=auth(token), json={
        "title": "La impresora hace un zumbido", "description": "zumbido raro", "priority": "p4_low",
        "ticket_type": "incident"})
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]["id"]


def _comentarios(db, tid):
    db.expire_all()
    return [c.body for c in db.query(TicketComment).filter(TicketComment.ticket_id == tid)]


def test_apagado_por_defecto_no_toca_nada(client, admin_token, db):
    tid = _ticket(client, admin_token)
    run_autonomous_scan(db)
    assert _comentarios(db, tid) == []
    assert db.query(AutonomousPlaybookExecution).count() == 0


def test_encendido_usa_el_playbook_de_la_organizacion_y_comenta_una_vez(client, admin_token, db):
    tid = _ticket(client, admin_token)
    org = db.query(Ticket).filter(Ticket.id == tid).one().organization_id
    db.add(AutonomousPlaybook(organization_id=org, name="Zumbidos", playbook_type="zumbido",
                              steps_json=json.dumps([{"type": "comment", "content": "Apaga y enciende la impresora"}]),
                              conditions_json=json.dumps({"trigger_keywords": ["zumbido"], "max_priority": "p3_medium"})))
    update_setting("SD_AUTONOMOUS_AGENT_ENABLED", "true", org, db)
    update_setting("SD_AUTONOMY_SUGGEST_THRESHOLD", "0.1", org, db)
    db.commit()

    run_autonomous_scan(db)
    run_autonomous_scan(db)

    assert _comentarios(db, tid) == ["Apaga y enciende la impresora"]
    filas = db.query(AutonomousPlaybookExecution).filter(AutonomousPlaybookExecution.ticket_id == tid).all()
    assert len(filas) == 1 and filas[0].triggered_by == "celery"
