"""Bolsa de horas de un contrato: lo usado sale de las imputaciones (revisión 2026-11).

Medido antes: `contracts.hours_used` no lo escribía ningún código y la bolsa
marcaba siempre 0 %.
"""
from __future__ import annotations

import uuid
from datetime import date

from app.models.imputation import Imputation
from app.models.pipeline import Contract
from app.models.project import Project, ProjectStatus, ProjectType
from tests.conftest import auth


def test_EL_HALLAZGO_la_bolsa_cuenta_lo_imputado_en_su_vigencia(client, db, admin_token):
    db.add(Project(id="p-bolsa", code="P-BOLSA", name="Bolsa", status=ProjectStatus.active,
                   project_type=ProjectType.consulting, organization_id="1"))
    c = Contract(id=str(uuid.uuid4()), code="CT-1", name="Soporte", client_name="Acme", project_id="p-bolsa", contract_type="hourly_bag",
                 status="active", hours_bag=40, start_date=date(2026, 10, 1), end_date=date(2026, 12, 31),
                 organization_id="1")
    db.add(c)
    for d, h in ((date(2026, 9, 30), 5), (date(2026, 10, 2), 6), (date(2026, 11, 5), 4)):   # la primera, fuera
        db.add(Imputation(id=str(uuid.uuid4()), user_id="pm-test-id", project_id="p-bolsa", date=d, hours=h,
                          organization_id="1", description="x"))
    db.commit()
    r = client.get("/api/v1/contracts", headers=auth(admin_token)).json()
    fila = next(x for x in (r.get("items") or r.get("data")) if x["id"] == c.id)
    assert (fila["hours_used"], fila["hours_pct"]) == (10.0, 25.0)
    una = client.get(f"/api/v1/contracts/{c.id}", headers=auth(admin_token)).json()["data"]
    assert una["hours_used"] == 10.0
