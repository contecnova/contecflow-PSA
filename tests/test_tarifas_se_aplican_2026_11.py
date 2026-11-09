"""Las tablas de tarifas se aplican al facturar (revisión 2026-11).

Medido antes: nadie leía las tarifas —facturas, rentabilidad e ingresos usaban
`projects.billing_rate`— y la búsqueda de tarifa efectiva reventaba en cuanto
una tarifa tenía vigencia (comparaba una fecha con un texto).
"""
from __future__ import annotations

import uuid
from datetime import date

from app.models.advanced_config import RateEntry, RateOverride, RateTable
from app.models.imputation import Imputation
from app.models.project import Project
from app.models.revenue import ASCMethod, RevenueContract
from app.models.user import User
from app.services import rate_card_service
from app.services.profitability_service import calc_project_profitability
from app.services.psa_flows import build_invoice_preview_from_timesheets_flow
from app.services.revenue_service import _recognize_over_time
from tests.test_presupuestos_2026_11 import proyecto  # noqa: F401  (fixture: p-b1)


def _datos(db):
    pm = db.query(User).filter(User.username == "pm_test").one()
    dev = db.query(User).filter(User.username == "dev_test").one()
    pm.job_title, dev.job_title = "Consultor senior", "Desarrollador"
    p = db.get(Project, "p-b1")
    p.billing_rate, p.is_billable = 50, True
    db.add(RateTable(id="rt-1", name="Estándar", is_default=True, is_active=True, organization_id="1"))
    db.add(RateEntry(table_id="rt-1", label="Consultor senior", billing_rate=100, escalation_pct=10,
                     valid_from=date(2025, 1, 1), organization_id="1"))
    db.add(RateEntry(table_id="rt-1", label="Desarrollador", billing_rate=70, valid_from=date(2025, 1, 1),
                     organization_id="1"))
    db.add(RateOverride(table_id="rt-1", project_id="p-b1", role_label="Desarrollador", billing_rate=80,
                        valid_from=date(2026, 1, 1), organization_id="1"))
    for u in (pm, dev):
        db.add(Imputation(id=str(uuid.uuid4()), user_id=u.id, project_id="p-b1", date=date(2026, 3, 2), hours=10,
                          is_billable=True, is_approved=True, organization_id="1", description="x"))
    db.commit()


def test_EL_HALLAZGO_la_busqueda_no_revienta_con_vigencia_y_escala(db, proyecto):
    _datos(db)
    r = rate_card_service.get_effective_rate(db, "Consultor senior", None, None, "2026-03-02", "1", False)
    assert r["billing_rate"] == 110.0          # 100 × 1,10: un año de escalado (vigente desde 2025, consulta de 2026)
    r = rate_card_service.get_effective_rate(db, "Desarrollador", None, "p-b1", "2026-03-02", "1", False)
    assert (r["billing_rate"], r["source"]) == (80, "override_project_id")


def test_EL_HALLAZGO_factura_rentabilidad_e_ingresos_usan_las_tarifas(db, proyecto):
    _datos(db)
    d = build_invoice_preview_from_timesheets_flow(db, "p-b1", None, None, 0)
    assert sorted((l["unit_price"], l["amount"]) for l in d["lines"]) == [(80.0, 800.0), (110.0, 1100.0)]
    assert calc_project_profitability(db.get(Project, "p-b1"), db)["billing_revenue"] == 1900.0
    c = RevenueContract(id="rc-1", organization_id="1", project_id="p-b1", name="T&M", contract_value=100000,
                        method=ASCMethod.over_time)
    db.add(c)
    db.commit()
    assert _recognize_over_time(db, c, 2026, 3, None) == 1900.0
