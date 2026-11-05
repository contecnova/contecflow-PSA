"""Facturas: ficha, edición de borradores y borrado (revisión 2026-11).

La pantalla sólo dejaba enviar, marcar como pagada y bajar el PDF; el backend
no tenía ni la ficha. Además el importe de cada línea lo mandaba el navegador.
"""
from __future__ import annotations

import uuid
from datetime import date

from app.models.imputation import Imputation
from app.models.project import Project, ProjectStatus, ProjectType
from app.models.user import User
from tests.conftest import auth

URL = "/api/v1/invoices"
LINEA = {"description": "Consultoría", "quantity": 10, "unit": "h", "unit_price": 50, "discount_pct": 10}


def _crear(client, token, **extra):
    r = client.post(URL, headers=auth(token), json={"client_name": "Acme", "issue_date": "2026-11-01", "tax_rate": 21,
                                                    "lines": [{**LINEA, "amount": 999999}], **extra})
    assert r.status_code == 201, r.text
    return r.json()["data"]


def test_EL_HALLAZGO_el_importe_lo_calcula_el_servidor(client, admin_token):
    f = _crear(client, admin_token)
    assert f["lines"][0]["amount"] == 450.0                      # 10 × 50 × 0,9 (no los 999999 que mandó)
    assert (f["subtotal"], f["tax_amount"], f["total"]) == (450.0, 94.5, 544.5)


def test_ficha_y_edicion_de_un_borrador(client, admin_token, pm_token):
    f = _crear(client, admin_token)
    ficha = client.get(f"{URL}/{f['id']}", headers=auth(pm_token)).json()["data"]
    assert ficha["number"] == f["number"] and len(ficha["lines"]) == 1
    r = client.patch(f"{URL}/{f['id']}", headers=auth(pm_token), json={
        "client_vat": "B12345678", "tax_rate": 10,
        "lines": [{**LINEA, "discount_pct": 0}, {"description": "Licencia", "quantity": 1, "unit": "u", "unit_price": 200}]})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert [l["amount"] for l in d["lines"]] == [500.0, 200.0]
    assert (d["subtotal"], d["tax_amount"], d["total"], d["client_vat"]) == (700.0, 70.0, 770.0, "B12345678")


def test_una_factura_emitida_no_se_toca(client, admin_token):
    f = _crear(client, admin_token)
    assert client.patch(f"/api/v1/billing-reports/invoices/{f['id']}/status", headers=auth(admin_token), json={"status": "sent"}).status_code == 200
    r = client.patch(f"{URL}/{f['id']}", headers=auth(admin_token), json={"notes": "x"})
    assert r.status_code == 409 and "anula" in r.json()["detail"]
    assert client.delete(f"{URL}/{f['id']}", headers=auth(admin_token)).status_code == 409


def test_borrar_un_borrador_libera_sus_horas(client, db, admin_token):
    u = db.query(User).filter(User.username == "dev_test").one()
    db.add(Project(id="p-fac", code="FAC", name="F", status=ProjectStatus.active, project_type=ProjectType.development,
                   organization_id="1"))
    imp = Imputation(id=str(uuid.uuid4()), user_id=u.id, project_id="p-fac", date=date(2026, 10, 1), hours=4,
                     organization_id="1", description="x")
    db.add(imp)
    db.commit()
    linea = {**LINEA, "source_type": "timesheet", "source_ids": [imp.id]}
    r = client.post(URL, headers=auth(admin_token), json={"client_name": "Acme", "issue_date": "2026-11-01",
                                                          "project_id": "p-fac", "lines": [linea]})
    fid = r.json()["data"]["id"]
    db.expire_all()
    assert db.get(Imputation, imp.id).invoiced_invoice_id == fid
    assert client.delete(f"{URL}/{fid}", headers=auth(admin_token)).status_code == 200
    db.expire_all()
    i = db.get(Imputation, imp.id)
    assert i.is_invoiced is False and i.invoiced_invoice_id is None
    assert client.get(f"{URL}/{fid}", headers=auth(admin_token)).status_code == 404


def test_solo_gestores(client, admin_token, dev_token):
    f = _crear(client, admin_token)
    assert client.get(f"{URL}/{f['id']}", headers=auth(dev_token)).status_code == 403
    assert client.patch(f"{URL}/{f['id']}", headers=auth(dev_token), json={"notes": "x"}).status_code == 403


def test_un_superadmin_crea_facturas_seguidas_con_numeros_distintos(client, db, superadmin_token):
    """Medido el 05-11-2026 en Postgres: crear una factura como el admin de la
    empresa (superadmin) daba 500. La secuencia se guardaba con su empresa (el
    sello) y se buscaba «sin empresa». El otro fallo de esa noche —fijar
    SERIALIZABLE después de la primera consulta— sólo existe en Postgres y se
    comprobó contra la copia de la base, no aquí."""
    from app.models.advanced_config import NumberingSequence
    a, b = _crear(client, superadmin_token), _crear(client, superadmin_token)
    assert a["number"] != b["number"]
    assert [s.organization_id for s in db.query(NumberingSequence).filter(NumberingSequence.entity == "invoice")] == ["1"]
