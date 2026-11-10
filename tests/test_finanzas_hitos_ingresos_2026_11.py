"""Pipeline, hitos, rentabilidad e ingresos (revisión 2026-11).

Medido antes:
- una oportunidad perdida se convertía en proyecto (y pasaba a ganada);
- quien pedía la aprobación de un hito la decidía;
- Rentabilidad marcaba un hito como facturado sin factura y lo completaba sin
  pasar por el flujo de facturación;
- un hito sólo con porcentaje, ya facturado, sumaba 0;
- el método de ingresos `completed_contract` reconocía 0 (desde la migración 156 vive en el motor
  ASC 606, con `percentage_complete`; el de hitos es el de sus obligaciones).
"""
from __future__ import annotations

from datetime import date

from app.models.revenue import ASCMethod, RevenueContract
from app.models.financial import ProjectMilestone
from app.models.project import Project
from app.services.revenue_service import _recognize_por_avance
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


def _contrato(db, pid, metodo):
    c = RevenueContract(organization_id="1", project_id=pid, name="C", contract_value=10000, method=metodo)
    db.add(c)
    db.commit()
    return c


def test_EL_HALLAZGO_el_contrato_terminado_se_reconoce_al_cerrar(client, pm_token, db):
    pid = _proyecto(client, pm_token, "FIN5")
    p = db.get(Project, pid)
    p.status = "completed"
    p.end_date_real = date(2031, 3, 20)
    db.commit()
    c = _contrato(db, pid, ASCMethod.completed_contract)
    assert _recognize_por_avance(db, c, 2031, 2, None) == 0
    assert _recognize_por_avance(db, c, 2031, 3, None) == 10000
    assert _recognize_por_avance(db, c, 2031, 3, None) == 0          # idempotente


def test_por_avance_reconoce_la_diferencia_cada_mes(client, pm_token, db):
    from app.models.task import Task, TaskStatus
    pid = _proyecto(client, pm_token, "FIN6")
    for i, estado in enumerate((TaskStatus.done, TaskStatus.todo, TaskStatus.todo, TaskStatus.cancelled)):
        db.add(Task(code=f"T-FIN6-{i}", project_id=pid, title=f"t{i}", status=estado))
    db.commit()
    c = _contrato(db, pid, ASCMethod.percentage_complete)
    assert _recognize_por_avance(db, c, 2031, 3, None) == 3333.33        # 1 de 3 (la cancelada no cuenta)
    t = db.query(Task).filter(Task.code == "T-FIN6-1").one()
    t.status = TaskStatus.done
    db.commit()
    assert _recognize_por_avance(db, c, 2031, 4, None) == 3333.34        # 2 de 3, menos lo ya reconocido
