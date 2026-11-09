"""El coste de un proyecto es personal + gastos + subcontrata (revisión 2026-11).

Medido antes: la rentabilidad y el AC de EVM sumaban sólo las imputaciones; los
gastos del proyecto y las horas de subcontratistas no llegaban a ningún margen,
y el real del presupuesto no veía la subcontrata.
"""
from __future__ import annotations

import uuid
from datetime import date

from app.models.bookings import ExchangeRate
from app.models.enterprise import Subcontractor, SubcontractorAssignment, SubcontractorTimeLog
from app.models.expenses import Expense, ExpenseAllocation, ExpenseStatus
from app.models.imputation import Imputation
from app.models.project import Project
from app.models.user import User
from app.services import project_service
from app.services.costes_de_proyecto import costes_externos
from app.services.profitability_service import calc_project_profitability
from tests.test_presupuestos_2026_11 import proyecto  # noqa: F401  (fixture: p-b1 y p-b2)


def _datos(db):
    pm = db.query(User).filter(User.username == "pm_test").one()
    db.add(Imputation(id=str(uuid.uuid4()), user_id=pm.id, project_id="p-b1", date=date(2026, 3, 2), hours=10,
                      cost_amount=500, organization_id="1", description="horas"))
    db.add(Expense(id="g-c", code="GC", user_id=pm.id, project_id="p-b1", category="travel", description="viaje",
                   amount=1000, currency="EUR", expense_date=date(2026, 3, 3), status=ExpenseStatus.approved,
                   organization_id="1"))
    db.add(ExpenseAllocation(expense_id="g-c", project_id="p-b1", percentage=30, organization_id="1"))
    db.add(ExpenseAllocation(expense_id="g-c", project_id="p-b2", percentage=70, organization_id="1"))
    db.add(Subcontractor(id="sub-1", code="SUB-1", name="Externa SL", currency="USD", organization_id="1"))
    db.add(SubcontractorAssignment(id="as-1", subcontractor_id="sub-1", project_id="p-b1", organization_id="1"))
    db.add(SubcontractorTimeLog(assignment_id="as-1", subcontractor_id="sub-1", project_id="p-b1", log_date=date(2026, 3, 4),
                                hours=4, cost_amount=200, organization_id="1", description="migración"))
    db.add(ExchangeRate(from_currency="USD", to_currency="EUR", rate=0.9, effective_date=date(2026, 1, 1)))
    db.commit()


def test_EL_HALLAZGO_gastos_y_subcontrata_entran_en_el_coste(db, proyecto):
    _datos(db)
    assert costes_externos(db, "p-b1", "EUR") == {"gastos": 300.0, "subcontrata": 180.0}
    r = calc_project_profitability(db.get(Project, "p-b1"), db)
    assert (r["internal_cost"], r["expenses_cost"], r["subcontract_cost"], r["total_cost"]) == (500, 300, 180, 980)
    assert r["ac"] == 980 and r["gross_margin"] == r["billing_revenue"] - 980
    assert project_service.calculate_evm("p-b1", db)["ac"] == 980


def test_el_real_del_presupuesto_ve_la_subcontrata(client, db, admin_token, proyecto, monkeypatch):
    from app.services import budgets_service
    from tests.conftest import auth
    from tests.test_presupuestos_2026_11 import URL, _crear
    monkeypatch.setattr(budgets_service, "_mes_actual", lambda: "2026-04")
    _datos(db)
    b = _crear(client, admin_token, periodo_hasta="2026-06-01")
    d = client.get(f"{URL}/{b['id']}", headers=auth(admin_token)).json()["data"]
    assert {x["tipo"]: x["real"] for x in d["informe"]["por_tipo"]}.get("subcontratacion") == 180   # 200 USD a 0,9
    r = client.get(f"{URL}/{b['id']}/drilldown", params={"mes": "2026-03", "tipo": "subcontratacion"}, headers=auth(admin_token)).json()
    assert [(x["origen"], x["quien"], x["importe"]) for x in r["items"]] == [("subcontrata", "Externa SL", 200.0)]
