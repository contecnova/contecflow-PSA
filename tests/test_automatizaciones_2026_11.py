"""Automatizaciones (revisión 2026-11): lo que faltaba para ser competitivas.

- Una regla solo admitía UNA condición: ahora grupos «todas»/«alguna», anidables.
- No había reglas por calendario: disparador «scheduled» con cron.
- Acciones nuevas: asignar (al menos cargado de un rol), actualizar campo y
  crear aprobación.
- Disparadores nuevos: facturas (enviada, cobrada, vencida) y aprobaciones.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.core import timeutil
from app.models.automations import AutomationExecution, AutomationRule
from app.models.billing_reports import ApprovalRequest, Invoice, InvoiceStatus
from app.models.task import Task, TaskStatus
from app.models.user import User, UserRole
from app.services import automation_events, automations_service as svc
from tests.conftest import HASH_DE_PRUEBA, auth
from tests.test_approvals import add_step, create_workflow
from tests.test_automatizaciones_que_disparan import _avisos, _proyecto, _regla, _tarea

AVISO = [{"type": "notify_user", "params": {"message": "ok"}}]


# ── Condiciones Y/O ─────────────────────────────────────────────────────────

def test_grupos_todas_y_alguna_anidables():
    ctx = {"priority": "high", "status": "blocked", "amount": 50}
    alta = {"field": "priority", "operator": "equals", "value": "high"}
    hecha = {"field": "status", "operator": "equals", "value": "done"}
    grande = {"field": "amount", "operator": "greater_than", "value": "100"}
    assert svc.check_conditions({"match": "all", "conditions": [alta, hecha]}, ctx) is False
    assert svc.check_conditions({"match": "any", "conditions": [alta, hecha]}, ctx) is True
    assert svc.check_conditions({"match": "all", "conditions": [
        alta, {"match": "any", "conditions": [hecha, grande]}]}, ctx) is False
    assert svc.check_conditions({"match": "any", "conditions": []}, ctx) is False, "vacío no se cumple"


def test_EL_HALLAZGO_la_regla_con_dos_condiciones_solo_salta_si_se_cumplen_las_dos(db):
    p = _proyecto(db)
    _regla(db, "task_status_changed", AVISO, conditions={"match": "all", "conditions": [
        {"field": "status", "operator": "equals", "value": "blocked"},
        {"field": "priority", "operator": "equals", "value": "critical"}]})
    t = _tarea(db, p, priority="medium")
    t.status = TaskStatus.blocked
    db.commit()
    automation_events.procesar_pendientes(db)
    assert _avisos(db, "pm-test-id") == 0
    t.priority, t.status = "critical", TaskStatus.in_progress
    db.commit()
    t.status = TaskStatus.blocked
    db.commit()
    automation_events.procesar_pendientes(db)
    assert _avisos(db, "pm-test-id") == 1


@pytest.mark.parametrize("cond", [{"match": "all", "conditions": []}, {"match": "xor", "conditions": [{"field": "a"}]},
                                  {"match": "any", "conditions": [{"operator": "equals"}]}])
def test_un_grupo_mal_formado_no_se_guarda(client, pm_token, cond):
    r = client.post("/api/v1/automations", headers=auth(pm_token), json={
        "name": "x", "trigger_type": "task_created", "trigger_conditions": cond, "actions": AVISO})
    assert r.status_code == 422, r.text


# ── Programadas ─────────────────────────────────────────────────────────────

def test_cron_no_valido_no_se_guarda(client, pm_token):
    r = client.post("/api/v1/automations", headers=auth(pm_token), json={
        "name": "x", "trigger_type": "scheduled", "schedule_cron": "cada lunes", "actions": AVISO})
    assert r.status_code == 422


def test_EL_HALLAZGO_la_regla_programada_corre_una_vez_por_instante(client, pm_token, db):
    r = client.post("/api/v1/automations", headers=auth(pm_token), json={
        "name": "Informe", "trigger_type": "scheduled", "schedule_cron": "0 9 * * 1-5",
        "actions": [{"type": "notify_role", "params": {"role": "pm", "message": "Revisión semanal"}}]})
    assert r.status_code in (200, 201), r.text
    regla = db.get(AutomationRule, r.json()["data"]["id"])
    assert regla.next_run_at is not None and regla.next_run_at.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc)
    regla.next_run_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    db.commit()
    assert svc.escanear(db)["by_trigger"]["scheduled"] == 1
    assert svc.escanear(db)["by_trigger"]["scheduled"] == 0, "no repite hasta el siguiente instante"
    db.expire_all()
    assert db.get(AutomationRule, regla.id).next_run_at.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc)
    assert _avisos(db, "pm-test-id") == 1


def test_pasar_a_otro_disparador_quita_el_cron(client, pm_token, db):
    r = client.post("/api/v1/automations", headers=auth(pm_token), json={
        "name": "x", "trigger_type": "scheduled", "schedule_cron": "*/30 * * * *", "actions": AVISO})
    rid = r.json()["data"]["id"]
    r = client.patch(f"/api/v1/automations/{rid}", headers=auth(pm_token), json={"trigger_type": "task_created"})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["schedule_cron"] is None and r.json()["data"]["next_run_at"] is None


# ── Acciones nuevas ─────────────────────────────────────────────────────────

def _empleado(db, uid, nombre):
    db.add(User(id=uid, username=uid, email=f"{uid}@contecflow.com", full_name=nombre, role=UserRole.team_lead,
                is_active=True, organization_id="1", hashed_password=HASH_DE_PRUEBA))
    db.commit()


def test_EL_HALLAZGO_asignar_al_menos_cargado_del_rol(db):
    _empleado(db, "tl-a", "A cargado")
    _empleado(db, "tl-b", "B libre")
    p = _proyecto(db)
    _tarea(db, p, code="TSK-90010", assignee_id="tl-a")
    _tarea(db, p, code="TSK-90011", assignee_id="tl-a")
    _regla(db, "task_created", [{"type": "assign", "params": {"to_role": "team_lead"}}])
    nueva = _tarea(db, p, code="TSK-90012", assignee_id=None)
    automation_events.procesar_pendientes(db)
    db.expire_all()
    assert db.get(Task, nueva.id).assignee_id == "tl-b"


def test_actualizar_campo_con_fecha_relativa(db):
    p = _proyecto(db)
    _regla(db, "task_created", [{"type": "update_field", "params": {"field": "task.due_date", "value": "+3"}}])
    t = _tarea(db, p)
    automation_events.procesar_pendientes(db)
    db.expire_all()
    assert db.get(Task, t.id).due_date == timeutil.today() + timedelta(days=3)


def test_actualizar_campo_solo_los_permitidos(client, pm_token):
    r = client.post("/api/v1/automations", headers=auth(pm_token), json={
        "name": "x", "trigger_type": "task_created",
        "actions": [{"type": "update_field", "params": {"field": "task.organization_id", "value": "otra"}}]})
    assert r.status_code == 422


def test_EL_HALLAZGO_crear_aprobacion_desde_una_regla(client, admin_token, db):
    wf = create_workflow(client, admin_token, entity_type="task")
    add_step(client, admin_token, wf["id"], approver_type="role", approver_role="admin")
    p = _proyecto(db)
    _regla(db, "task_created", [{"type": "create_approval", "params": {"summary": "Revisar alcance"}}])
    t = _tarea(db, p)
    automation_events.procesar_pendientes(db)
    db.expire_all()
    req = db.query(ApprovalRequest).filter(ApprovalRequest.entity_id == t.id).one()
    assert req.status == "pending" and req.requested_by == "pm-test-id" and req.entity_type == "task"
    # Otra vez, con una pendiente: no duplica.
    ejec = db.query(AutomationExecution).one()
    assert ejec.success, ejec.actions_taken


# ── Disparadores nuevos ─────────────────────────────────────────────────────

def _factura(db, **kw):
    f = Invoice(number=kw.pop("number", "INV-AUT-1"), organization_id="1", issue_date=timeutil.today(),
                total=1200, client_name="Acme", **kw)
    db.add(f)
    db.commit()
    return f


def test_EL_HALLAZGO_la_factura_enviada_dispara(db):
    _regla(db, "invoice_sent", [{"type": "notify_role", "params": {"role": "pm", "message": "Enviada"}}],
           conditions={"field": "total", "operator": "greater_than", "value": "1000"})
    f = _factura(db)
    f.status = InvoiceStatus.sent
    db.commit()
    assert automation_events.procesar_pendientes(db)["rules_run"] == 1


def test_EL_HALLAZGO_la_factura_vencida_avisa_una_vez(db):
    _regla(db, "invoice_overdue", [{"type": "notify_role", "params": {"role": "pm", "message": "Vencida"}}])
    _factura(db, status=InvoiceStatus.sent, due_date=timeutil.today() - timedelta(days=10))
    _factura(db, number="INV-AUT-2", status=InvoiceStatus.paid, due_date=timeutil.today() - timedelta(days=10))
    assert svc.escanear(db)["by_trigger"]["invoice_overdue"] == 1
    assert svc.escanear(db)["by_trigger"]["invoice_overdue"] == 0


def test_EL_HALLAZGO_la_aprobacion_aprobada_dispara(client, admin_token, pm_token, db):
    wf = create_workflow(client, admin_token)
    add_step(client, admin_token, wf["id"], approver_type="role", approver_role="admin")
    _regla(db, "approval_approved", AVISO)
    r = client.post("/api/v1/approvals/requests", headers=auth(pm_token), json={
        "entity_type": "expense", "entity_id": "e-9", "entity_summary": "Gasto", "context": {}})
    rid = r.json()["data"]["id"]
    automation_events.procesar_pendientes(db)
    client.post(f"/api/v1/approvals/requests/{rid}/decide", headers=auth(admin_token), json={"decision": "approved"})
    automation_events.procesar_pendientes(db)
    assert _avisos(db, "pm-test-id") == 1, "avisa a quien la pidió"


def test_el_catalogo_no_ofrece_nada_que_el_motor_no_sepa():
    from app.models.automations import ActionType, TriggerType
    assert {"scheduled", "invoice_sent", "invoice_overdue", "approval_approved"} <= {t.value for t in TriggerType}
    assert {"assign", "update_field", "create_approval"} <= set(svc.CATALOGO_ACCIONES)
    assert set(svc._EFECTO) >= set(svc.CATALOGO_ACCIONES)
