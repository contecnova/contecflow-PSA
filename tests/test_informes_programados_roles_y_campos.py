"""Informes programados: solo responsables y sin asignacion masiva.

Auditoria 2026-11: cualquier usuario listaba los informes de su organizacion
con sus destinatarios, y el PATCH copiaba cualquier campo del cuerpo
(`organization_id` incluido).
"""
from app.models.billing_reports import ScheduledReport
from tests.conftest import auth

BASE = "/api/v1/billing-reports/scheduled-reports"


def _crear(client, token):
    r = client.post(BASE, headers=auth(token), json={"name": "Semanal", "recipients": ["jefa@acme-demo.com"]})
    assert r.status_code == 201, r.text
    return r.json()["data"]["id"]


def test_un_empleado_no_lista_los_programados(client, pm_token, dev_token):
    _crear(client, pm_token)
    assert client.get(BASE, headers=auth(pm_token)).status_code == 200
    assert client.get(BASE, headers=auth(dev_token)).status_code == 403


def test_el_patch_solo_cambia_campos_editables(client, pm_token, db):
    rid = _crear(client, pm_token)
    org = db.query(ScheduledReport).filter(ScheduledReport.id == rid).one().organization_id
    r = client.patch(f"{BASE}/{rid}", headers=auth(pm_token), json={"organization_id": "otra-org"})
    assert r.status_code == 422, r.text
    r = client.patch(f"{BASE}/{rid}", headers=auth(pm_token), json={"name": "Mensual", "frequency": "monthly"})
    assert r.status_code == 200, r.text
    db.expire_all()
    fila = db.query(ScheduledReport).filter(ScheduledReport.id == rid).one()
    assert (fila.name, fila.frequency, fila.organization_id) == ("Mensual", "monthly", org)
