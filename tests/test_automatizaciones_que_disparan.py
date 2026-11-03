"""Las reglas de automatizacion saltan solas, dentro de su organizacion.

Auditoria 2026-11. Antes: `fire_trigger()` no tenia quien lo llamara, «Probar»
ejecutaba las acciones de verdad, 52 de los 64 disparadores de la pantalla no
se podian guardar, «pausar» era borrar, y avisar a un rol avisaba a ese rol en
todas las organizaciones.
"""
from __future__ import annotations

import json
from datetime import timedelta

import pytest

from app.core import timeutil
from app.models.automations import AutomationEvent, AutomationExecution, AutomationRule
from app.models.enterprise import Notification
from app.models.alert import Alert
from app.models.project import Project, ProjectStatus, ProjectType
from app.models.task import Task, TaskStatus
from app.models.user import User, UserRole, UserStatus
from app.services import automation_events, automations_service as svc
from tests.conftest import auth

ORG = "1"
OTRA = "org-ajena"


def _proyecto(db, org=ORG, code="AUT1"):
    p = Project(code=code, name="Auto", status=ProjectStatus.active, project_type=ProjectType.development,
                organization_id=org)
    db.add(p)
    db.commit()
    return p


def _tarea(db, proyecto, **kw):
    t = Task(code=kw.pop("code", "TSK-90001"), title="T", project_id=proyecto.id,
             organization_id=proyecto.organization_id, assignee_id=kw.pop("assignee_id", "pm-test-id"), **kw)
    db.add(t)
    db.commit()
    return t


def _regla(db, trigger, actions, org=ORG, conditions=None, activa=True):
    r = AutomationRule(name=f"R {trigger}", trigger_type=trigger, organization_id=org, is_active=activa,
                       actions=json.dumps(actions),
                       trigger_conditions=json.dumps(conditions) if conditions else None)
    db.add(r)
    db.commit()
    return r


def _ajeno(db):
    u = User(id="pm-ajeno", username="pm_ajeno", email="pm@ajena.test", full_name="PM ajeno",
             role=UserRole.pm, status=UserStatus.active, is_active=True, hashed_password="x",
             organization_id=OTRA)
    db.add(u)
    db.commit()
    return u


def _avisos(db, user_id):
    return db.query(Notification).filter(Notification.user_id == user_id, Notification.type == "automation").count()


# ── Salta sola ──────────────────────────────────────────────────────────────

def test_EL_HALLAZGO_cambiar_una_tarea_dispara_la_regla_sin_pulsar_nada(client, pm_token, db):
    p = _proyecto(db)
    t = _tarea(db, p)
    _regla(db, "task_status_changed", [{"type": "notify_user", "params": {"message": "Hecha"}}],
           conditions={"field": "status", "operator": "equals", "value": "done"})

    r = client.patch(f"/api/v1/tasks/{t.id}", json={"status": "done"}, headers=auth(pm_token))
    assert r.status_code == 200, r.text

    eventos = db.query(AutomationEvent).filter(AutomationEvent.trigger_type == "task_status_changed").all()
    assert len(eventos) == 1, "el cambio de estado no dejo evento en la bandeja"
    assert automation_events.procesar_pendientes(db)["rules_run"] == 1
    assert _avisos(db, "pm-test-id") == 1
    db.refresh(eventos[0])
    assert eventos[0].status == "done"


def test_sin_regla_no_se_anota_nada(client, pm_token, db):
    p = _proyecto(db)
    t = _tarea(db, p)
    client.patch(f"/api/v1/tasks/{t.id}", json={"status": "done"}, headers=auth(pm_token))
    assert db.query(AutomationEvent).count() == 0


def test_la_condicion_que_no_se_cumple_no_ejecuta(db):
    p = _proyecto(db)
    t = _tarea(db, p)
    _regla(db, "task_status_changed", [{"type": "notify_user", "params": {"message": "x"}}],
           conditions={"field": "status", "operator": "equals", "value": "done"})
    t.status = TaskStatus.in_progress
    db.commit()
    automation_events.procesar_pendientes(db)
    assert _avisos(db, "pm-test-id") == 0


def test_un_ticket_P1_se_escala_al_crearse(client, admin_token, db):
    _regla(db, "ticket_created", [{"type": "escalate_ticket", "params": {"to_level": "l2"}}],
           conditions={"field": "priority", "operator": "equals", "value": "p1_critical"})
    r = client.post("/api/v1/sd/tickets", headers=auth(admin_token), json={
        "title": "Caida", "description": "x", "priority": "p1_critical", "ticket_type": "incident"})
    assert r.status_code in (200, 201), r.text
    automation_events.procesar_pendientes(db)
    from app.models.service_desk import Ticket
    ticket = db.query(Ticket).filter(Ticket.id == r.json()["data"]["id"]).first()
    db.refresh(ticket)
    assert ticket.support_level.value == "l2"


# ── Una organizacion ────────────────────────────────────────────────────────

def test_EL_HALLAZGO_la_regla_de_otra_organizacion_no_salta(db):
    p = _proyecto(db)
    t = _tarea(db, p)
    _regla(db, "task_status_changed", [{"type": "notify_role", "params": {"role": "pm", "message": "x"}}], org=OTRA)
    t.status = TaskStatus.done
    db.commit()
    assert db.query(AutomationEvent).count() == 0
    assert svc.disparar(db, "task_status_changed", {"task_id": t.id}, ORG)["rules"] == []


def test_EL_HALLAZGO_avisar_a_un_rol_no_sale_de_la_organizacion(db):
    _ajeno(db)
    _regla(db, "expense_submitted", [{"type": "notify_role", "params": {"role": "pm", "message": "Gasto"}}])
    svc.disparar(db, "expense_submitted", {"user_id": "dev-test-id"}, ORG)
    db.commit()
    assert _avisos(db, "pm-test-id") == 1
    assert _avisos(db, "pm-ajeno") == 0, "el aviso llego a un PM de otra organizacion"


@pytest.mark.parametrize("metodo,sufijo", [
    ("patch", ""), ("delete", ""), ("post", "/test"), ("get", "/executions")])
def test_EL_HALLAZGO_por_id_no_se_alcanza_la_regla_de_otra_organizacion(client, pm_token, db, metodo, sufijo):
    ajena = _regla(db, "task_created", [{"type": "create_alert", "params": {"message": "x"}}], org=OTRA)
    kwargs = {"json": {"name": "robada"}} if metodo == "patch" else {}
    r = getattr(client, metodo)(f"/api/v1/automations/{ajena.id}{sufijo}", headers=auth(pm_token), **kwargs)
    assert r.status_code in (403, 404), r.text
    db.refresh(ajena)
    assert ajena.name != "robada"


# ── Lo que se guarda ────────────────────────────────────────────────────────

@pytest.mark.parametrize("cuerpo,motivo", [
    ({"trigger_type": "git_pr_merged", "actions": [{"type": "create_alert", "params": {"message": "x"}}]}, "Disparador"),
    ({"trigger_type": "task_created", "actions": [{"type": "rpa_uipath", "params": {}}]}, "tipo desconocido"),
    ({"trigger_type": "task_created", "actions": [{"type": "notify_role", "params": {"message": "x"}}]}, "role"),
    ({"trigger_type": "task_created", "actions": [{"type": "send_email", "params": {"subject": "x"}}]}, "to"),
    ({"trigger_type": "task_created", "actions": []}, "al menos una"),
])
def test_EL_HALLAZGO_no_se_guarda_lo_que_el_motor_no_sabe_hacer(client, pm_token, db, cuerpo, motivo):
    r = client.post("/api/v1/automations", json={"name": "x", **cuerpo}, headers=auth(pm_token))
    assert r.status_code == 422, r.text
    assert motivo in r.text


def test_el_catalogo_de_la_pantalla_es_el_del_motor(client, pm_token, db):
    r = client.get("/api/v1/automations/catalog", headers=auth(pm_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert {t["type"] for t in data["triggers"]} == set(svc.CATALOGO_DISPARADORES)
    assert {a["type"] for a in data["actions"]} == set(svc.CATALOGO_ACCIONES)
    for a in data["actions"]:
        assert svc._ACCIONES.get(a["type"]), f"{a['type']} se ofrece y no tiene ejecutor"


def test_EL_HALLAZGO_pausar_no_es_borrar(client, pm_token, db):
    r = client.post("/api/v1/automations", headers=auth(pm_token), json={
        "name": "Pausable", "trigger_type": "task_created",
        "actions": [{"type": "create_alert", "params": {"message": "x"}}]})
    rid = r.json()["data"]["id"]
    assert client.patch(f"/api/v1/automations/{rid}", json={"is_active": False},
                        headers=auth(pm_token)).status_code == 200
    todas = client.get("/api/v1/automations", headers=auth(pm_token)).json()["items"]
    assert [x["is_active"] for x in todas if x["id"] == rid] == [False], "la regla pausada desaparecio"
    assert client.patch(f"/api/v1/automations/{rid}", json={"is_active": True},
                        headers=auth(pm_token)).status_code == 200


# ── «Probar» simula ─────────────────────────────────────────────────────────

def test_EL_HALLAZGO_probar_no_ejecuta_nada(client, pm_token, db):
    r = client.post("/api/v1/automations", headers=auth(pm_token), json={
        "name": "Ruidosa", "trigger_type": "task_created",
        "actions": [{"type": "notify_role", "params": {"role": "pm", "message": "x"}},
                    {"type": "create_alert", "params": {"message": "x"}}]})
    rid = r.json()["data"]["id"]
    res = client.post(f"/api/v1/automations/{rid}/test", headers=auth(pm_token)).json()["data"]
    assert res["simulated"] is True
    assert "1 usuario" in res["results"][0]["would"]
    assert db.query(Notification).count() == 0
    assert db.query(Alert).count() == 0
    assert db.query(AutomationExecution).count() == 0


# ── Barrido ─────────────────────────────────────────────────────────────────

def test_EL_HALLAZGO_la_tarea_vencida_avisa_una_vez_y_no_en_cada_pasada(db):
    p = _proyecto(db)
    _tarea(db, p, due_date=timeutil.today() - timedelta(days=3), status=TaskStatus.todo)
    _regla(db, "task_overdue", [{"type": "notify_user", "params": {"message": "Vencida"}}])
    assert svc.escanear(db)["by_trigger"]["task_overdue"] == 1
    assert svc.escanear(db)["by_trigger"]["task_overdue"] == 0
    assert _avisos(db, "pm-test-id") == 1


def test_el_interruptor_apaga_las_reglas(db):
    from app.services import settings_service
    p = _proyecto(db)
    _tarea(db, p, due_date=timeutil.today() - timedelta(days=1), status=TaskStatus.todo)
    _regla(db, "task_overdue", [{"type": "notify_user", "params": {"message": "x"}}])
    settings_service.set_runtime_value(db, "automations", "AUTOMATIONS_ENABLED", False, ORG)
    db.commit()
    assert svc.escanear(db)["executed"] == 0


# ── Cadenas y condiciones ───────────────────────────────────────────────────

def test_una_regla_que_se_dispara_a_si_misma_se_corta(db):
    p = _proyecto(db)
    t = _tarea(db, p, status=TaskStatus.todo)
    _regla(db, "task_status_changed", [{"type": "change_task_status", "params": {"status": "in_progress"}}],
           conditions={"field": "status", "operator": "equals", "value": "todo"})
    _regla(db, "task_status_changed", [{"type": "change_task_status", "params": {"status": "todo"}}],
           conditions={"field": "status", "operator": "equals", "value": "in_progress"})
    t.status = TaskStatus.in_progress
    db.commit()
    for _ in range(10):
        if not automation_events.procesar_pendientes(db)["events"]:
            break
    assert db.query(AutomationEvent).filter(AutomationEvent.status == "pending").count() == 0
    assert db.query(AutomationExecution).count() <= 4


def test_lo_que_no_se_puede_evaluar_no_se_cumple():
    assert svc.check_conditions({"field": "x", "operator": "inventado", "value": "1"}, {"x": "1"}) is False
    assert svc.check_conditions({"field": "x", "operator": "greater_than", "value": "a"}, {"x": "3"}) is False
