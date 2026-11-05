"""Núcleo de aprobaciones: lo que la revisión del 05-11-2026 encontró roto.

- Las condiciones del flujo (por importe, departamento) solo las usaba la
  simulación: la solicitud cogía siempre el flujo por defecto.
- Delegar avisaba al delegado, pero la bandeja le devolvía 403.
- Solo se avisaba a un usuario concreto o al primero del rol, y solo en la
  aplicación: con grupo, departamento o responsable no se avisaba a nadie.
- `reminder_hours` se guardaba y nadie lo leía.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.models.billing_reports import ApprovalRequest, ApprovalWorkflow
from app.models.enterprise import Notification
from tests.conftest import auth
from tests.test_approvals import add_step, create_workflow


@pytest.fixture
def correos(monkeypatch):
    enviados = []
    monkeypatch.setattr("app.services.notification_service.send_email_notification",
                        lambda to, subject, body: enviados.append(to) or True)
    return enviados


def _pedir(client, token, contexto=None, entity_id="e-1"):
    r = client.post("/api/v1/approvals/requests", headers=auth(token), json={
        "entity_type": "expense", "entity_id": entity_id, "entity_summary": "Gasto", "context": contexto or {}})
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]


def test_EL_HALLAZGO_la_solicitud_va_al_flujo_cuyas_condiciones_encajan(client, admin_token, pm_token, db):
    general = create_workflow(client, admin_token, name="General")
    add_step(client, admin_token, general["id"])
    grande = create_workflow(client, admin_token, is_default=False, name="Más de 1000")
    add_step(client, admin_token, grande["id"])
    db.query(ApprovalWorkflow).filter(ApprovalWorkflow.id == grande["id"]).update(
        {"trigger_conditions": json.dumps({"amount_gt": 1000})})
    db.commit()
    assert _pedir(client, pm_token, {"amount": 2500}, "e-big")["workflow_id"] == grande["id"]
    assert _pedir(client, pm_token, {"amount": 200}, "e-small")["workflow_id"] == general["id"]


def test_EL_HALLAZGO_el_delegado_puede_decidir(client, admin_token, pm_token, dev_token, db):
    wf = create_workflow(client, admin_token)
    add_step(client, admin_token, wf["id"], approver_type="role", approver_role="admin")
    req = _pedir(client, pm_token)
    r = client.post(f"/api/v1/approvals/requests/{req['id']}/decide", headers=auth(admin_token),
                    json={"decision": "delegated", "delegate_to": "dev-test-id", "note": "vacaciones"})
    assert r.status_code == 200, r.text
    bandeja = client.get("/api/v1/approvals/requests/pending-my-action", headers=auth(dev_token)).json()
    assert req["id"] in [x["id"] for x in bandeja.get("items", bandeja.get("data", []))]
    r = client.post(f"/api/v1/approvals/requests/{req['id']}/decide", headers=auth(dev_token),
                    json={"decision": "approved"})
    assert r.status_code == 200, r.text


def test_EL_HALLAZGO_se_avisa_a_todos_los_del_rol_y_por_correo(client, admin_token, dev_token, db, correos):
    from app.models.user import User, UserRole
    from tests.conftest import HASH_DE_PRUEBA
    db.add(User(id="pm-2", username="pm2", email="pm2@contecflow.com", full_name="PM 2", role=UserRole.pm,
                is_active=True, organization_id="1", hashed_password=HASH_DE_PRUEBA))
    db.commit()
    wf = create_workflow(client, admin_token)
    add_step(client, admin_token, wf["id"], approver_type="role", approver_role="pm")
    req = _pedir(client, dev_token)
    avisados = {n.user_id for n in db.query(Notification).filter(Notification.resource_id == req["id"]).all()}
    assert avisados == {"pm-test-id", "pm-2"}
    assert sorted(correos) == ["pm2@contecflow.com", "pm@contecflow.com"]


def test_EL_HALLAZGO_se_avisa_al_responsable(client, admin_token, dev_token, db, correos):
    from app.models.user import User
    db.query(User).filter(User.id == "dev-test-id").update({"manager_id": "pm-test-id"})
    db.commit()
    wf = create_workflow(client, admin_token)
    r = client.post(f"/api/v1/approvals/workflows/{wf['id']}/steps", headers=auth(admin_token), json={
        "step_order": 1, "name": "Responsable", "approver_type": "manager", "timeout_hours": 48})
    assert r.status_code in (200, 201), r.text
    req = _pedir(client, dev_token)
    assert {n.user_id for n in db.query(Notification).filter(Notification.resource_id == req["id"])} == {"pm-test-id"}


def test_EL_HALLAZGO_los_recordatorios_se_envian(client, admin_token, pm_token, db, correos):
    from app.models.billing_reports import ApprovalStep
    from app.services.approval_engine.timeouts import process_approval_timeouts
    wf = create_workflow(client, admin_token)
    paso = add_step(client, admin_token, wf["id"], approver_type="role", approver_role="admin")
    db.query(ApprovalStep).filter(ApprovalStep.id == paso["id"]).update({"reminder_hours": 1})
    req = _pedir(client, pm_token)
    db.query(ApprovalRequest).filter(ApprovalRequest.id == req["id"]).update(
        {"step_started_at": datetime.now(timezone.utc) - timedelta(hours=2)})
    db.commit()
    antes = db.query(Notification).filter(Notification.resource_id == req["id"]).count()
    process_approval_timeouts(db)
    db.expire_all()
    assert db.query(Notification).filter(Notification.resource_id == req["id"]).count() > antes
    assert db.get(ApprovalRequest, req["id"]).last_reminder_at is not None
    # No se repite antes de que vuelva a tocar.
    despues = db.query(Notification).filter(Notification.resource_id == req["id"]).count()
    process_approval_timeouts(db)
    assert db.query(Notification).filter(Notification.resource_id == req["id"]).count() == despues


# ── Aprobar desde el correo ──────────────────────────────────────────────────

@pytest.fixture
def enlaces(monkeypatch):
    vistos = []
    monkeypatch.setattr("app.services.notification_service.send_email_notification",
                        lambda to, subject, body: vistos.append((to, body)) or True)
    return vistos


def _token_de(enlaces, correo):
    import re
    cuerpo = next(b for t, b in enlaces if t == correo)
    return re.search(r"/approvals/decide\?token=([^\s]+)", cuerpo).group(1)


def test_EL_HALLAZGO_se_aprueba_desde_el_enlace_del_correo_sin_sesion(client, admin_token, pm_token, db, enlaces):
    wf = create_workflow(client, admin_token)
    add_step(client, admin_token, wf["id"], approver_type="role", approver_role="admin")
    req = _pedir(client, pm_token)
    token = _token_de(enlaces, "admin@contecflow.com")
    client.cookies.clear()
    r = client.get("/api/v1/approvals/email-decision", params={"token": token})
    assert r.status_code == 200 and r.json()["data"]["request_id"] == req["id"]
    db.expire_all()
    assert db.get(ApprovalRequest, req["id"]).status == "pending", "abrir el enlace no decide"
    assert client.post("/api/v1/approvals/email-decision", json={"token": token, "decision": "rejected"}).status_code == 422
    r = client.post("/api/v1/approvals/email-decision", json={"token": token, "decision": "approved"})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(ApprovalRequest, req["id"]).status == "approved"
    assert client.post("/api/v1/approvals/email-decision", json={"token": token, "decision": "approved"}).status_code == 410


def test_un_enlace_manipulado_no_vale(client, db):
    r = client.post("/api/v1/approvals/email-decision", json={"token": "x.y.z", "decision": "approved"})
    assert r.status_code == 410


def test_el_solicitante_no_se_aprueba_a_si_mismo_por_correo(client, admin_token, db, enlaces):
    from app.services.approval_engine.por_correo import crear_enlace
    wf = create_workflow(client, admin_token)
    add_step(client, admin_token, wf["id"], approver_type="role", approver_role="admin")
    req = _pedir(client, admin_token)
    fila = db.get(ApprovalRequest, req["id"])
    token = crear_enlace(db, fila, "admin-test-id").split("token=")[1]
    r = client.post("/api/v1/approvals/email-decision", json={"token": token, "decision": "approved"})
    assert r.status_code == 403


def test_EL_HALLAZGO_la_aprobacion_pendiente_llega_al_canal(client, admin_token, pm_token, db, enlaces, monkeypatch):
    from app.services import integrations
    eventos = []
    monkeypatch.setattr(integrations, "notify_event", lambda tipo, entidad, db, *a, **k: eventos.append((tipo, entidad["id"])))
    wf = create_workflow(client, admin_token)
    add_step(client, admin_token, wf["id"], approver_type="role", approver_role="admin")
    req = _pedir(client, pm_token)
    assert eventos == [("approval.required", req["id"])]


# ── Fuera de la oficina ──────────────────────────────────────────────────────

def _ausencia(client, token, delegado, dias=(-1, 3)):
    from datetime import date
    hoy = date.today()
    return client.put("/api/v1/approvals/out-of-office", headers=auth(token), json={
        "delegate_id": delegado, "away_from": (hoy + timedelta(days=dias[0])).isoformat(),
        "away_until": (hoy + timedelta(days=dias[1])).isoformat()})


def test_EL_HALLAZGO_el_delegado_de_un_ausente_recibe_y_decide(client, admin_token, pm_token, dev_token, db, correos):
    assert _ausencia(client, admin_token, "dev-test-id").status_code == 200
    wf = create_workflow(client, admin_token)
    add_step(client, admin_token, wf["id"], approver_type="role", approver_role="admin")
    req = _pedir(client, pm_token)
    avisados = {n.user_id for n in db.query(Notification).filter(Notification.resource_id == req["id"])}
    assert "dev-test-id" in avisados and "admin-test-id" in avisados
    r = client.post(f"/api/v1/approvals/requests/{req['id']}/decide", headers=auth(dev_token), json={"decision": "approved"})
    assert r.status_code == 200, r.text


def test_fuera_de_fechas_el_delegado_no_decide(client, admin_token, pm_token, dev_token, db, correos):
    _ausencia(client, admin_token, "dev-test-id", dias=(5, 9))
    wf = create_workflow(client, admin_token)
    add_step(client, admin_token, wf["id"], approver_type="role", approver_role="admin")
    req = _pedir(client, pm_token)
    r = client.post(f"/api/v1/approvals/requests/{req['id']}/decide", headers=auth(dev_token), json={"decision": "approved"})
    assert r.status_code == 403


def test_delegaciones_cruzadas_no_entran_en_bucle(client, admin_token, hr_token, pm_token, db, correos):
    from app.services.approval_engine._base import _is_authorized
    from app.models.billing_reports import ApprovalStep
    from app.models.user import User
    _ausencia(client, admin_token, "hr-test-id")
    _ausencia(client, hr_token, "admin-test-id")
    paso = ApprovalStep(step_order=1, name="x", approver_type="role", approver_role="pm")
    assert _is_authorized(paso, db.get(User, "hr-test-id"), "otro", db) is False
