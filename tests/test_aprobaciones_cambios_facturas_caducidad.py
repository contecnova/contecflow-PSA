"""Cambios y facturas en la bandeja, y la caducidad que llega a la entidad.

Auditoria 2026-11: los cambios de /changes y las facturas no abrian solicitud;
el rechazo por caducidad no tocaba la entidad; auto-aprobar o escalar el ultimo
paso dejaba la solicitud colgada; escalar se saltaba el paso; y `auto_reject`
(el valor que documentaba la API) no lo reconocia el job.
"""
from datetime import datetime, timedelta, timezone

from app.models.billing_reports import ApprovalRequest, ApprovalStep, Invoice
from app.models.expenses import Expense
from app.models.resources import ChangeRequest
from app.services.approval_engine.timeouts import process_approval_timeouts
from tests.conftest import auth
from tests.test_approvals import create_workflow
from tests.test_bandeja_gastos_horas_ausencias import _bandeja, _gasto_enviado


def _flujo(client, admin_token, tipo, **paso):
    wf = create_workflow(client, admin_token, entity_type=tipo, is_default=True)
    r = client.post(f"/api/v1/approvals/workflows/{wf['id']}/steps", headers=auth(admin_token), json={
        "step_order": 1, "name": "Paso 1", "approver_type": "role", "approver_role": "admin",
        "timeout_hours": 1, **paso})
    assert r.status_code in (200, 201), r.text
    return wf, r.json()["data"]


def _caducar(db, entidad_id):
    req = db.query(ApprovalRequest).filter(ApprovalRequest.entity_id == entidad_id).one()
    req.step_started_at = datetime.now(timezone.utc) - timedelta(hours=2)
    db.commit()
    return req


def _cambio_enviado(client, pm_token):
    pid = client.post("/api/v1/projects", headers=auth(pm_token), json={
        "name": "CR", "code": "CRP1", "status": "active", "billing_type": "time_material"}).json()["data"]["id"]
    r = client.post(f"/api/v1/changes/{pid}", headers=auth(pm_token), json={
        "title": "Ampliar alcance", "description": "Nuevo modulo", "cost_impact": 3000})
    assert r.status_code in (200, 201), r.text
    cid = r.json()["data"]["id"]
    r = client.post(f"/api/v1/changes/{pid}/{cid}/submit", headers=auth(pm_token))
    assert r.status_code == 200, r.text
    return pid, cid


# ── Cambios ─────────────────────────────────────────────────────────────────

def test_EL_HALLAZGO_el_cambio_enviado_llega_a_la_bandeja_y_su_decision_lo_aprueba(client, admin_token, pm_token, db):
    _flujo(client, admin_token, "change_request")
    _, cid = _cambio_enviado(client, pm_token)
    pendiente = next(p for p in _bandeja(client, admin_token) if p["entity_id"] == cid)
    r = client.post(f"/api/v1/approvals/requests/{pendiente['id']}/decide",
                    json={"decision": "approved"}, headers=auth(admin_token))
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.query(ChangeRequest).filter(ChangeRequest.id == cid).one().status.value == "approved"


def test_revisar_el_cambio_en_su_pantalla_cierra_la_solicitud(client, admin_token, pm_token, db):
    _flujo(client, admin_token, "change_request")
    pid, cid = _cambio_enviado(client, pm_token)
    r = client.post(f"/api/v1/changes/{pid}/{cid}/review", headers=auth(admin_token),
                    json={"approved": False, "resolution_notes": "Fuera de alcance"})
    assert r.status_code == 200, r.text
    assert [p for p in _bandeja(client, admin_token) if p["entity_id"] == cid] == []


# ── Facturas ────────────────────────────────────────────────────────────────

def _factura(client, admin_token):
    r = client.post("/api/v1/billing-reports/invoices", headers=auth(admin_token), json={
        "client_name": "Acme", "issue_date": "2026-11-01"})
    if r.status_code == 404:
        r = client.post("/api/v1/invoices", headers=auth(admin_token), json={"client_name": "Acme", "issue_date": "2026-11-01"})
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]["id"]


def _enviar(client, token, iid):
    for ruta in (f"/api/v1/billing-reports/invoices/{iid}/status", f"/api/v1/invoices/{iid}/status"):
        r = client.patch(ruta, json={"status": "sent"}, headers=auth(token))
        if r.status_code != 404:
            return r
    return r


def test_sin_flujo_la_factura_se_envia_como_siempre(client, admin_token, db):
    iid = _factura(client, admin_token)
    assert _enviar(client, admin_token, iid).status_code == 200


def test_EL_HALLAZGO_con_flujo_la_factura_pasa_por_la_bandeja_antes_de_enviarse(client, admin_token, pm_token, db):
    # Aprueba un PM: quien pide no puede aprobar lo suyo (segregacion de funciones).
    _flujo(client, admin_token, "invoice", approver_role="pm")
    iid = _factura(client, admin_token)
    r = _enviar(client, admin_token, iid)
    assert r.status_code == 409 and "aprobación" in r.text
    db.expire_all()
    assert db.query(Invoice).filter(Invoice.id == iid).one().status.value == "draft"
    assert _enviar(client, admin_token, iid).status_code == 409   # sigue pendiente, no abre otra
    pendientes = [p for p in _bandeja(client, pm_token) if p["entity_id"] == iid]
    assert len(pendientes) == 1
    r = client.post(f"/api/v1/approvals/requests/{pendientes[0]['id']}/decide",
                    json={"decision": "approved"}, headers=auth(pm_token))
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.query(Invoice).filter(Invoice.id == iid).one().status.value == "sent"


# ── Caducidad ───────────────────────────────────────────────────────────────

def test_EL_HALLAZGO_el_rechazo_por_caducidad_llega_al_gasto(client, admin_token, dev_token, db):
    _flujo(client, admin_token, "expense", on_timeout="reject")
    gid = _gasto_enviado(client, dev_token)
    _caducar(db, gid)
    assert process_approval_timeouts(db)["rejected"] == 1
    db.expire_all()
    assert db.query(Expense).filter(Expense.id == gid).one().status.value == "rejected"


def test_EL_HALLAZGO_auto_aprobar_el_ultimo_paso_cierra_y_aprueba(client, admin_token, dev_token, db):
    _flujo(client, admin_token, "expense", on_timeout="auto_approve")
    gid = _gasto_enviado(client, dev_token)
    req = _caducar(db, gid)
    process_approval_timeouts(db)
    db.expire_all()
    assert db.query(ApprovalRequest).filter(ApprovalRequest.id == req.id).one().status == "approved"
    assert db.query(Expense).filter(Expense.id == gid).one().status.value == "approved"


def test_EL_HALLAZGO_escalar_no_se_salta_el_paso_y_quien_recibe_puede_decidir(client, admin_token, pm_token, dev_token, db):
    _flujo(client, admin_token, "expense", on_timeout="escalate", escalate_to_user_id="pm-test-id")
    gid = _gasto_enviado(client, dev_token)
    req = _caducar(db, gid)
    assert process_approval_timeouts(db)["escalated"] == 1
    db.expire_all()
    req = db.query(ApprovalRequest).filter(ApprovalRequest.id == req.id).one()
    assert req.status == "pending" and req.current_step == 1
    pendiente = next(p for p in _bandeja(client, pm_token) if p["entity_id"] == gid)
    r = client.post(f"/api/v1/approvals/requests/{pendiente['id']}/decide",
                    json={"decision": "approved"}, headers=auth(pm_token))
    assert r.status_code == 200, r.text
    # Si vuelve a caducar ya escalado, se rechaza en vez de escalar sin fin.


def test_una_segunda_caducidad_tras_escalar_rechaza(client, admin_token, dev_token, db):
    _flujo(client, admin_token, "expense", on_timeout="escalate", escalate_to_user_id="pm-test-id")
    gid = _gasto_enviado(client, dev_token)
    _caducar(db, gid)
    process_approval_timeouts(db)
    _caducar(db, gid)
    assert process_approval_timeouts(db)["rejected"] == 1
    db.expire_all()
    assert db.query(Expense).filter(Expense.id == gid).one().status.value == "rejected"


def test_auto_reject_se_acepta_como_reject_y_lo_inventado_no(client, admin_token, db):
    wf = create_workflow(client, admin_token, entity_type="expense", is_default=False, name="x")
    base = {"step_order": 1, "name": "P", "approver_type": "role", "approver_role": "admin"}
    r = client.post(f"/api/v1/approvals/workflows/{wf['id']}/steps", headers=auth(admin_token),
                    json={**base, "on_timeout": "auto_reject"})
    assert r.status_code in (200, 201), r.text
    assert db.query(ApprovalStep).filter(ApprovalStep.workflow_id == wf["id"]).one().on_timeout == "reject"
    r = client.post(f"/api/v1/approvals/workflows/{wf['id']}/steps", headers=auth(admin_token),
                    json={**base, "step_order": 2, "on_timeout": "quemar"})
    assert r.status_code == 422
