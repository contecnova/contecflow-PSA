"""Métricas y listas de gastos por proyecto cuentan el reparto (revisión 2026-11).

Medido antes: filtradas por proyecto miraban el proyecto propio del gasto: un
gasto de 1.000 repartido 60/40 salía entero en su proyecto y nada en el otro.
Por categoría y facturable sumaban además borradores y rechazados; la tendencia
dejaba fuera los reembolsados. Y la herramienta de gastos del asistente leía
`e.date`, que no existe.
"""
from __future__ import annotations

from datetime import date

from app.models.expenses import Expense, ExpenseAllocation, ExpenseStatus
from app.models.user import User
from app.services import expense_service
from app.services.metrics import revenue_expenses as m
from tests.test_presupuestos_2026_11 import proyecto  # noqa: F401  (fixture: p-b1 y p-b2)

D, H = date(2026, 1, 1), date(2026, 12, 31)


def _gastos(db):
    pm = db.query(User).filter(User.username == "pm_test").one()
    db.add(Expense(id="g-rep", code="G1", user_id=pm.id, project_id="p-b1", category="travel", description="viaje",
                   amount=1000, expense_date=date(2026, 3, 2), status=ExpenseStatus.approved, organization_id="1",
                   is_billable=True))
    db.add(ExpenseAllocation(expense_id="g-rep", project_id="p-b1", percentage=60, organization_id="1"))
    db.add(ExpenseAllocation(expense_id="g-rep", project_id="p-b2", percentage=40, organization_id="1"))
    db.add(Expense(id="g-borr", code="G2", user_id=pm.id, project_id="p-b2", category="travel", description="borrador",
                   amount=999, expense_date=date(2026, 3, 3), status=ExpenseStatus.draft, organization_id="1"))
    db.add(Expense(id="g-reem", code="G3", user_id=pm.id, project_id="p-b2", category="meals", description="comida",
                   amount=50, expense_date=date(2026, 4, 3), status=ExpenseStatus.reimbursed, organization_id="1"))
    db.commit()
    return pm


def test_EL_HALLAZGO_las_metricas_por_proyecto_cuentan_su_parte(db, proyecto):
    _gastos(db)
    filas, _ = m.metric_expenses_by_category(db, D, H, 10, project_id="p-b2")
    assert {f["label"]: f["value"] for f in filas} == {"travel": 400.0, "meals": 50.0}
    filas, _ = m.metric_expenses_billable_vs_internal(db, D, H, 10, project_ids=["p-b1"])
    assert {f["label"]: f["value"] for f in filas} == {"Facturable": 600.0}
    filas, _ = m.metric_expenses_trend(db, D, H, 10, project_ids=["p-b2"])
    assert filas == [{"label": "2026-03", "value": 400.0}, {"label": "2026-04", "value": 50.0}]


def test_la_herramienta_del_asistente_no_revienta(db, proyecto):
    from datetime import datetime

    from app.services.ai_chat.tool_execution.finance import _get_expenses
    pm = _gastos(db)
    r = _get_expenses({"project_id": "p-b2"}, db, pm, datetime.now(), True)
    assert {e["id"] for e in r["expenses"]} == {"g-rep", "g-borr", "g-reem"} and r["expenses"][0]["date"]
