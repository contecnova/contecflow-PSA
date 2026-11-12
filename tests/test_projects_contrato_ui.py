"""Auditoria 2026-11 (#25): contrato entre ProjectsPage/ProjectDetailPage y la API.

- El alta descartaba `status`, `risk_level`, `billing_type` y `retainer_*`.
- La edicion descartaba `billing_type` y `retainer_*`: la facturacion recurrente
  (app/worker.py, generate_retainer_invoices) no se podia configurar desde la UI.
- El detalle no traia `pm_name`, que es lo que lee la pantalla.
"""
from tests.conftest import auth


def test_alta_guarda_estado_riesgo_y_retainer(client, pm_token, db):
    res = client.post("/api/v1/projects", json={
        "name": "Retainer UI", "status": "active", "risk_level": "high",
        "billing_type": "recurring_retainer", "retainer_amount": "1500", "retainer_day": 5,
    }, headers=auth(pm_token))
    assert res.status_code in (200, 201), res.text
    data = res.json()["data"]
    assert data["status"] == "active"
    assert data["risk_level"] == "high"
    assert data["billing_type"] == "recurring_retainer"
    assert data["retainer_amount"] == 1500
    assert data["retainer_day"] == 5
    # Un retainer recurrente sin is_billable explicito queda facturable: el worker lo exige.
    assert data["is_billable"] is True


def test_edicion_guarda_retainer_y_detalle_trae_pm_name(client, pm_token, db):
    pid = client.post("/api/v1/projects", json={"name": "Edicion UI"},
                      headers=auth(pm_token)).json()["data"]["id"]
    res = client.patch(f"/api/v1/projects/{pid}", json={
        "billing_type": "recurring_retainer", "retainer_amount": 900, "retainer_day": 28,
    }, headers=auth(pm_token))
    assert res.status_code == 200, res.text

    det = client.get(f"/api/v1/projects/{pid}", headers=auth(pm_token)).json()["data"]
    assert det["billing_type"] == "recurring_retainer"
    assert det["retainer_amount"] == 900
    assert det["retainer_day"] == 28
    assert det["is_billable"] is True
    # El PM que crea queda como PM del proyecto; el detalle expone su nombre.
    assert det["pm_name"]
    assert det["pm_name"] == det["project_manager"]["full_name"]


def test_retainer_day_fuera_de_rango_es_422(client, pm_token, db):
    res = client.post("/api/v1/projects", json={
        "name": "Dia malo", "billing_type": "recurring_retainer", "retainer_day": 31,
    }, headers=auth(pm_token))
    assert res.status_code == 422
