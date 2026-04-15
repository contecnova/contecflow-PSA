"""Tests de rentabilidad — EAC/ETC/CPI y métricas EVM."""
from datetime import date

from app.models.bookings import ExchangeRate
from app.models.imputation import Imputation
from app.models.user import User
from tests.conftest import auth

def make_project(client, token):
    r = client.post("/api/v1/projects", json={
        "name":"P EVM","code":"EVM","status":"active",
        "billing_type":"time_material","budget_amount":50000,"billing_rate":120,
    }, headers=auth(token))
    return r.json()["id"]

def test_profitability_summary(client, admin_token, db):
    res = client.get("/api/v1/profitability/summary", headers=auth(admin_token))
    assert res.status_code == 200
    data = res.json()
    assert "projects" in data or "summary" in data or isinstance(data, list)

def test_profitability_project_detail(client, pm_token, db):
    pid = make_project(client, pm_token)
    res = client.get(f"/api/v1/profitability/{pid}", headers=auth(pm_token))
    assert res.status_code == 200
    data = res.json()
    # Verificar que devuelve métricas EVM
    assert "margin_pct" in data
    assert "eac" in data
    assert "cpi" in data
    assert "etc" in data

def test_evm_values_are_numeric(client, pm_token, db):
    pid = make_project(client, pm_token)
    res = client.get(f"/api/v1/profitability/{pid}", headers=auth(pm_token))
    data = res.json()
    for field in ["eac", "etc", "vac", "margin_pct"]:
        assert isinstance(data.get(field), (int, float, type(None))), f"{field} no es numérico"

def test_profitability_requires_auth(client, db):
    res = client.get("/api/v1/profitability/summary")
    assert res.status_code in (401, 403)


def test_profitability_converts_internal_cost_to_project_currency(client, pm_token, db):
    pid = make_project(client, pm_token)

    dev = db.query(User).filter(User.id == "dev-test-id").first()
    dev.currency = "USD"
    db.add(ExchangeRate(
        from_currency="USD",
        to_currency="EUR",
        rate=0.9,
        effective_date=date.today(),
        source="manual",
    ))
    db.add(Imputation(
        user_id=dev.id,
        task_id=None,
        project_id=pid,
        date=date.today(),
        hours=1.0,
        is_billable=True,
        hourly_rate_snapshot=100.0,
        cost_amount=100.0,
    ))
    db.commit()

    res = client.get(f"/api/v1/profitability/{pid}", headers=auth(pm_token))
    assert res.status_code == 200
    data = res.json()
    assert data["internal_cost"] == 90.0
