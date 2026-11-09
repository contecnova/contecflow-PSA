"""Pipeline, hitos, rentabilidad e ingresos (revisión 2026-11).

Medido antes:
- una oportunidad perdida se convertía en proyecto (y pasaba a ganada);
- quien pedía la aprobación de un hito la decidía;
- Rentabilidad marcaba un hito como facturado sin factura y lo completaba sin
  pasar por el flujo de facturación;
- un hito sólo con porcentaje, ya facturado, sumaba 0;
- los métodos de ingresos `milestone` y `completed_contract` reconocían 0.
"""
from __future__ import annotations

from datetime import date

from app.models.cab import RecognitionMethod, RevenueRecognitionRule
from app.models.financial import ProjectMilestone
from app.models.project import Project
from app.services.cab_service import compute_revenue_period
from tests.conftest import auth


def _proyecto(client, token, code, **extra):
    r = client.post("/api/v1/projects", headers=auth(token), json={
        "name": f"P {code}", "code": code, "status": "active", "billing_type": "fixed_price",
        "contract_amount": 50000, **extra})
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]["id"]


def _hito(client, token, pid, **campos):
    r = client.post(f"/api/v1/milestones/project/{pid}", headers=auth(token), json={"name": "Fase", **campos})
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]["id"]


def test_EL_HALLAZGO_una_oportunidad_perdida_no_se_convierte(client, admin_token, db):
    r = client.post("/api/v1/pipeline", headers=auth(admin_token),
                    json={"name": "Perdida", "client_name": "Cliente", "stage": "lost", "expected_revenue": 1000})
    assert r.status_code in (200, 201), r.text
    r = client.post(f"/api/v1/pipeline/{r.json()['data']['id']}/convert", headers=auth(admin_token))
    assert r.status_code == 400, r.text


def test_EL_HALLAZGO_quien_pide_la_aprobacion_del_hito_no_la_decide(client, pm_token, db):
    pid = _proyecto(client, pm_token, "FIN1")
    mid = _hito(client, pm_token, pid, billing_amount=1000)
    client.post(f"/api/v1/milestones/{mid}/complete", headers=auth(pm_token))
    client.post(f"/api/v1/milestones/{mid}/request-approval", headers=auth(pm_token))
    r = client.post(f"/api/v1/milestones/{mid}/approve", json={"approved": True}, headers=auth(pm_token))
    assert r.status_code == 403, r.text


def test_EL_HALLAZGO_rentabilidad_no_factura_a_mano_y_completa_por_el_flujo(client, pm_token, db):
    pid = _proyecto(client, pm_token, "FIN2")
    mid = _hito(client, pm_token, pid, billing_amount=1000)
    r = client.patch(f"/api/v1/profitability/{pid}/milestones/{mid}", headers=auth(pm_token), json={"is_billed": True})
    assert r.status_code == 400, r.text
    r = client.patch(f"/api/v1/profitability/{pid}/milestones/{mid}", headers=auth(pm_token), json={"is_completed": True})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(ProjectMilestone, mid).billing_status == "completed"


def test_EL_HALLAZGO_el_hito_por_porcentaje_guarda_lo_facturado(client, pm_token, admin_token, db):
    pid = _proyecto(client, pm_token, "FIN3", budget_amount=20000)
    mid = _hito(client, pm_token, pid, billing_pct=25)
    client.post(f"/api/v1/milestones/{mid}/complete", headers=auth(pm_token))
    client.post(f"/api/v1/milestones/{mid}/request-approval", headers=auth(pm_token))
    client.post(f"/api/v1/milestones/{mid}/approve", json={"approved": True}, headers=auth(admin_token))
    r = client.post(f"/api/v1/milestones/{mid}/generate-invoice", headers=auth(pm_token))
    assert r.status_code == 200, r.text
    db.expire_all()
    hito = db.get(ProjectMilestone, mid)
    assert hito.billing_status == "invoiced" and hito.billing_amount and hito.billing_amount > 0


def _regla(db, pid, metodo):
    regla = RevenueRecognitionRule(project_id=pid, method=metodo, contract_value=10000)
    db.add(regla)
    db.commit()
    return regla


def test_EL_HALLAZGO_el_metodo_por_hitos_reconoce_los_del_mes(client, pm_token, db):
    pid = _proyecto(client, pm_token, "FIN4")
    db.add(ProjectMilestone(project_id=pid, name="Hecho", billing_amount=3000, is_completed=True,
                            completed_date=date(2031, 3, 10), billing_status="completed"))
    db.commit()
    r = compute_revenue_period(_regla(db, pid, RecognitionMethod.milestone).id, "2031-03-01", db)
    assert r["amount_recognised"] == 3000


def test_EL_HALLAZGO_el_contrato_terminado_se_reconoce_al_cerrar(client, pm_token, db):
    pid = _proyecto(client, pm_token, "FIN5")
    p = db.get(Project, pid)
    p.status = "completed"
    p.end_date_real = date(2031, 3, 20)
    db.commit()
    regla = _regla(db, pid, RecognitionMethod.completed_contract)
    assert compute_revenue_period(regla.id, "2031-02-01", db)["amount_recognised"] == 0
    assert compute_revenue_period(regla.id, "2031-03-01", db)["amount_recognised"] == 10000
