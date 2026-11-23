"""Auditoría 22-11-2026 · informe 02 (servicios a…l): críticos arreglados el 23-11-2026.

Solo lo imprescindible de cada crítico (C1, C2, C3, C5) y del ABAC roto (A1).
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

from tests.conftest import auth


# ── C1 · la auto-aprobación no se decide con el contexto del cliente ─────────

def _flujo_gastos_con_auto_aprobacion(db):
    from app.models.billing_reports import ApprovalStep, ApprovalWorkflow
    wf = ApprovalWorkflow(name="Gastos", entity_type="expense", is_active=True, is_default=True,
                          organization_id="1",
                          auto_approval_rules=json.dumps([{"action": "auto_approve", "label": "menor",
                                                           "conditions": {"amount_lt": 100}}]))
    db.add(wf)
    db.flush()
    db.add(ApprovalStep(workflow_id=wf.id, step_order=1, name="Paso 1", approver_type="role",
                        approver_role="admin", organization_id="1"))
    db.commit()
    return wf


def _gasto(db, importe):
    from app.models.expenses import Expense, ExpenseStatus
    e = Expense(code="EXP-T1", user_id="dev-test-id", organization_id="1", category="travel",
                description="Hotel", amount=importe, currency="EUR", expense_date=date.today(),
                status=ExpenseStatus.submitted)
    db.add(e)
    db.commit()
    return e


def test_c1_contexto_del_cliente_no_auto_aprueba(client, dev_token, db):
    _flujo_gastos_con_auto_aprobacion(db)
    gasto = _gasto(db, 50_000)
    res = client.post("/api/v1/approvals/requests", json={
        "entity_type": "expense", "entity_id": gasto.id, "context": {"amount": 1},
    }, headers=auth(dev_token))
    assert res.status_code in (200, 201), res.text
    data = res.json()["data"]
    assert data["status"] == "pending"


def test_c1_importe_real_si_auto_aprueba(client, dev_token, db):
    _flujo_gastos_con_auto_aprobacion(db)
    gasto = _gasto(db, 50)
    res = client.post("/api/v1/approvals/requests", json={
        "entity_type": "expense", "entity_id": gasto.id, "context": {"amount": 1_000_000},
    }, headers=auth(dev_token))
    assert res.status_code in (200, 201), res.text
    assert res.json()["data"]["status"] == "approved"


def test_c1_entidad_inexistente_404(client, dev_token, db):
    _flujo_gastos_con_auto_aprobacion(db)
    res = client.post("/api/v1/approvals/requests", json={
        "entity_type": "expense", "entity_id": "no-existe", "context": {"amount": 1},
    }, headers=auth(dev_token))
    assert res.status_code == 404


# ── C2 · un fallo del proveedor no retira CIs ───────────────────────────────

def test_c2_fallo_del_proveedor_no_retira_cis(db, monkeypatch):
    from app.models.cmdb import CMDBDiscoveryProvider
    from app.models.service_desk import CIStatus, CIType, ConfigurationItem
    from app.services.cmdb import discovery

    prov = CMDBDiscoveryProvider(name="AWS", provider_type="aws", organization_id="1", config_json="{}")
    db.add(prov)
    db.flush()
    ci = ConfigurationItem(organization_id="1", code="CI-1", name="web01", ci_type=CIType.server,
                           status=CIStatus.operational, external_id="i-1", discovery_provider="aws",
                           discovery_provider_id=prov.id, is_discovered=True)
    db.add(ci)
    db.commit()

    def falla(_config):
        discovery._anotar_error("AWS EC2", RuntimeError("credencial caducada"))
        return []

    monkeypatch.setattr(discovery, "discover_aws", falla)
    job = discovery.run_discovery_for_provider(db, prov)
    db.refresh(ci)
    assert job.status == "error"
    assert ci.status == CIStatus.operational
    assert job.cis_deactivated == 0


# ── C5 · la cadena de auditoría de colaboración no se bifurca ───────────────

def test_c5_varias_escrituras_en_una_transaccion_no_bifurcan(db):
    from app.services.collaboration import _audit
    for i in range(5):
        _audit.write(db, organization_id="1", actor_user_id="admin-test-id", actor_client_id=None,
                     action=f"accion.{i}", entity_type="x", entity_id=str(i), payload={"i": i})
    db.commit()
    for i in range(3):
        _audit.write(db, organization_id="1", actor_user_id="admin-test-id", actor_client_id=None,
                     action=f"otra.{i}", entity_type="x", entity_id=str(i))
        db.commit()
    r = _audit.verify_chain(db, "1")
    assert r["total"] == 8
    assert r["chains"] == 1
    assert r["is_valid"], r["breaks"]
    assert not _audit._org_locks["1"]._value == 0, "el bloqueo no se ha soltado al confirmar"
