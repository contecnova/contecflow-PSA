"""Un solo margen (auditoría 22-11-2026, §7.2): panel, rentabilidad, EVM, BI y la
evolución del margen dan la MISMA cifra, también con varias monedas, y el
cálculo en bloque hace las mismas consultas con 2 proyectos que con 6.
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import event

from app.models.bookings import ExchangeRate
from app.models.enterprise import Subcontractor, SubcontractorAssignment, SubcontractorTimeLog
from app.models.expenses import Expense, ExpenseStatus
from app.models.imputation import Imputation
from app.models.project import Project, ProjectStatus, ProjectType
from app.models.user import User
from tests.test_presupuestos_2026_11 import proyecto  # noqa: F401  (fixture: p-b1 y p-b2 de la empresa "1")

DIA = date(2026, 3, 2)


def _datos(db):
    """p-b1 (EUR, 100 €/h facturable): 10 h de una persona en USD (500 USD de
    coste), un gasto de 100 GBP y un parte de subcontrata de 200 USD.
    Tipos: USD→EUR 0,9 directo; GBP solo como EUR→GBP 0,8 (inverso)."""
    pm = db.query(User).filter(User.username == "pm_test").one()
    pm.currency = "USD"
    p = db.get(Project, "p-b1")
    p.currency, p.billing_rate, p.is_billable = "EUR", 100.0, True
    db.add(Imputation(id=str(uuid.uuid4()), user_id=pm.id, project_id="p-b1", date=DIA, hours=10,
                      cost_amount=500, is_billable=True, organization_id="1", description="horas"))
    db.add(Imputation(id=str(uuid.uuid4()), user_id=pm.id, project_id="p-b1", date=DIA, hours=99,
                      cost_amount=9999, is_billable=True, organization_id="1", description="borrada",
                      is_active=False))
    db.add(Expense(id="g-m1", code="GM1", user_id=pm.id, project_id="p-b1", category="travel", description="viaje",
                   amount=100, currency="GBP", expense_date=DIA, status=ExpenseStatus.approved, organization_id="1"))
    db.add(Subcontractor(id="sub-m1", code="SUB-M1", name="Externa SL", currency="USD", organization_id="1"))
    db.add(SubcontractorAssignment(id="as-m1", subcontractor_id="sub-m1", project_id="p-b1", organization_id="1"))
    db.add(SubcontractorTimeLog(assignment_id="as-m1", subcontractor_id="sub-m1", project_id="p-b1", log_date=DIA,
                                hours=4, cost_amount=200, organization_id="1", description="migración"))
    db.add(ExchangeRate(from_currency="USD", to_currency="EUR", rate=0.9, effective_date=date(2026, 1, 1)))
    db.add(ExchangeRate(from_currency="EUR", to_currency="GBP", rate=0.8, effective_date=date(2026, 1, 1)))
    db.commit()


def test_las_cinco_pantallas_dan_el_mismo_margen_con_varias_monedas(db, proyecto):
    from app.core.periodo import resolver_periodo
    from app.services import evolucion_del_margen
    from app.services.dashboard_service import get_profitability
    from app.services.evm_service import coste_real
    from app.services.margen_de_proyectos import margen_en_bloque
    from app.services.metrics.costs import metric_margin_by_project
    from app.services.profitability_service import calc_project_profitability

    _datos(db)
    proj = db.get(Project, "p-b1")
    c = margen_en_bloque(db, [proj])["p-b1"]
    # 500 USD × 0,9 = 450 € · 100 GBP / 0,8 = 125 € · 200 USD × 0,9 = 180 € · la borrada no cuenta.
    assert (c["internal_cost"], c["expenses_cost"], c["subcontract_cost"]) == (450.0, 125.0, 180.0)
    assert c["total_cost"] == 755.0 and c["revenue"] == 1000.0 and c["margin"] == 245.0
    assert c["fx_warnings"] == []

    pl = calc_project_profitability(proj, db)
    assert (pl["billing_revenue"], pl["total_cost"], pl["gross_margin"]) == (1000.0, 755.0, 245.0)

    panel = {r["project_id"]: r for r in get_profitability(None, None, db)}["p-b1"]
    assert (panel["revenue"], panel["total_cost"], panel["margin"], panel["margin_pct"]) == (
        1000.0, 755.0, 245.0, pl["margin_pct"])

    assert coste_real(db, "p-b1") == 755.0                                   # AC del EVM

    filas, _ = metric_margin_by_project(db, date(2026, 1, 1), date(2026, 12, 31), 10, project_ids=["p-b1"])
    assert filas[0]["margin"] == pl["margin_pct"]                           # BI

    periodo = resolver_periodo(desde="2026-03-01", hasta="2026-03-31", granularidad="month",
                               ahora=__import__("datetime").datetime(2026, 4, 1, tzinfo=__import__("datetime").timezone.utc))
    fila = evolucion_del_margen.desglose(db, "1", periodo, "proyecto", proyecto_id="p-b1")[0]
    assert (fila["revenue"], fila["total_cost"], fila["margin"]) == (1000.0, 755.0, 245.0)


def test_sin_tipo_se_avisa_y_no_se_esconde(db, proyecto):
    from app.services.margen_de_proyectos import margen_en_bloque
    pm = db.query(User).filter(User.username == "pm_test").one()
    pm.currency = "JPY"
    db.add(Imputation(id=str(uuid.uuid4()), user_id=pm.id, project_id="p-b1", date=DIA, hours=1,
                      cost_amount=1000, organization_id="1", description="horas"))
    db.commit()
    c = margen_en_bloque(db, [db.get(Project, "p-b1")])["p-b1"]
    assert c["fx_warnings"] == [f"JPY→EUR@{DIA.isoformat()}"]


def test_el_bloque_no_crece_con_el_numero_de_proyectos(db, proyecto):
    from app.services.margen_de_proyectos import margen_en_bloque
    _datos(db)
    pm = db.query(User).filter(User.username == "pm_test").one()
    for i in range(4):
        pid = f"p-m{i}"
        db.add(Project(id=pid, code=pid.upper(), name=pid, status=ProjectStatus.active, billing_rate=80.0,
                       is_billable=True, project_type=ProjectType.development, organization_id="1"))
        db.flush()
        db.add(Imputation(id=str(uuid.uuid4()), user_id=pm.id, project_id=pid, date=date(2026, 3, 1 + i), hours=2,
                          cost_amount=100, is_billable=True, organization_id="1", description="horas"))
    db.commit()

    def contar(ids):
        proyectos = db.query(Project).filter(Project.id.in_(ids)).all()
        n = 0

        def _cuenta(*_a):
            nonlocal n
            n += 1
        event.listen(db.bind, "before_cursor_execute", _cuenta)
        try:
            margen_en_bloque(db, proyectos)
        finally:
            event.remove(db.bind, "before_cursor_execute", _cuenta)
        return n

    assert contar(["p-b1", "p-m0"]) >= contar(["p-b1", "p-b2", "p-m0", "p-m1", "p-m2", "p-m3"])
