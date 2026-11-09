"""Anular o borrar una factura devuelve sus horas e hitos a «por facturar» (revisión 2026-11).

Medido antes: anular no soltaba las horas (`is_invoiced`) ni los hitos
(`billing_status="invoiced"`): no se podían volver a facturar nunca.
"""
from __future__ import annotations

import uuid
from datetime import date

from app.models.billing_reports import Invoice
from app.models.financial import ProjectMilestone
from app.models.imputation import Imputation
from app.models.project import Project, ProjectStatus, ProjectType
from tests.conftest import auth


def _montar(db, estado):
    db.add(Project(id="p-fact", code="P-FACT", name="F", status=ProjectStatus.active,
                   project_type=ProjectType.consulting, organization_id="1"))
    inv = Invoice(id=str(uuid.uuid4()), number="INV-L1", project_id="p-fact", organization_id="1",
                  client_name="C", issue_date=date(2026, 11, 1), status=estado, total=100)
    db.add(inv); db.flush()
    imp = Imputation(id=str(uuid.uuid4()), user_id="pm-test-id", project_id="p-fact", date=date(2026, 10, 3),
                     hours=4, organization_id="1", description="x", is_invoiced=True, invoiced_invoice_id=inv.id)
    hito = ProjectMilestone(id=str(uuid.uuid4()), project_id="p-fact", name="Hito", organization_id="1",
                            billing_status="invoiced", invoice_id=inv.id, is_billed=True, billed_at=date(2026, 11, 1))
    db.add_all([imp, hito]); db.commit()
    return inv, imp, hito


def _libres(db, imp, hito):
    db.expire_all()
    i, h = db.get(Imputation, imp.id), db.get(ProjectMilestone, hito.id)
    return (i.is_invoiced, i.invoiced_invoice_id, h.billing_status, h.invoice_id, h.is_billed)


def test_EL_HALLAZGO_anular_suelta_horas_e_hitos(client, db, admin_token):
    inv, imp, hito = _montar(db, "sent")
    r = client.patch(f"/api/v1/billing-reports/invoices/{inv.id}/status", headers=auth(admin_token), json={"status": "cancelled"})
    assert r.status_code == 200, r.text
    assert _libres(db, imp, hito) == (False, None, "approved", None, False)


def test_borrar_un_borrador_suelta_tambien_los_hitos(client, db, admin_token):
    inv, imp, hito = _montar(db, "draft")
    assert client.delete(f"/api/v1/invoices/{inv.id}", headers=auth(admin_token)).status_code in (200, 204)
    assert _libres(db, imp, hito) == (False, None, "approved", None, False)
