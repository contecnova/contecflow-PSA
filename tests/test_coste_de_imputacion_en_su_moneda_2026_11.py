"""El coste de una imputación se guarda en la moneda de la empresa (revisión 2026-11).

Medido antes: se guardaba horas × coste/hora del perfil en la moneda del perfil,
y la conversión que existía (`cost_service.cost_amount`) no la llamaba nadie;
la rentabilidad «convertía» por una moneda del usuario que no existe.
"""
from __future__ import annotations

from datetime import date

from app.models.bookings import ExchangeRate
from app.models.imputation import Imputation
from app.models.task import Task, TaskPriority, TaskStatus
from app.models.user_cost import UserCostProfile
from tests.conftest import auth
from tests.test_imputation_business_guards import _create_project


def test_EL_HALLAZGO_un_perfil_en_dolares_se_imputa_en_euros(client, admin_token, dev_token, db):
    project_id = _create_project(client, admin_token, "IMPFX-1")
    task = Task(code="TASK-IMPFX", project_id=project_id, title="t", assignee_id="dev-test-id",
                status=TaskStatus.in_progress, priority=TaskPriority.medium)
    db.add(task)
    db.add(UserCostProfile(user_id="dev-test-id", organization_id="1", currency="USD", gross_annual_salary=1,
                           employer_cost_pct=0, extra_annual_costs=0, productive_hours_year=1700,
                           total_annual_cost=1, cost_per_hour=100, valid_from=date(2020, 1, 1)))
    db.add(ExchangeRate(from_currency="USD", to_currency="EUR", rate=0.9, effective_date=date(2020, 1, 1)))
    db.commit()
    r = client.post("/api/v1/imputations", headers=auth(dev_token),
                    json={"project_id": project_id, "task_id": task.id, "date": str(date.today()), "hours": 2})
    assert r.status_code == 200, r.text
    imp = db.get(Imputation, r.json()["data"]["id"])
    assert (imp.hourly_rate_snapshot, imp.cost_amount) == (100, 180.0)      # 2 h × 100 USD × 0,9
    r = client.patch(f"/api/v1/imputations/{imp.id}", headers=auth(dev_token), json={"hours": 3})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(Imputation, imp.id).cost_amount == 270.0                  # el tipo queda congelado
