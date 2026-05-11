"""Tests de Gastos — CRUD, aprobación, recibos."""
from tests.conftest import auth

from app.models.advanced_config import NumberingSequence
from app.models.expenses import Expense


def _get_project_id(client, token):
    res = client.get("/api/v1/projects", headers=auth(token))
    projects = res.json() if isinstance(res.json(), list) else res.json().get("items", [])
    if projects:
        return projects[0]["id"]
    create = client.post("/api/v1/projects",
        headers=auth(token),
        json={"name": "Proyecto gastos test", "code": "EXP-01",
              "start_date": "2025-01-01", "end_date": "2025-12-31"})
    return create.json()["id"]


def test_list_expenses(client, admin_token, db):
    res = client.get("/api/v1/expenses", headers=auth(admin_token))
    assert res.status_code == 200


def test_create_expense(client, admin_token, db):
    res = client.post("/api/v1/expenses",
        headers=auth(admin_token),
        json={"description": "Vuelo Madrid-Barcelona", "amount": 145.50,
              "category": "travel", "expense_date": "2025-03-15",
              "currency": "EUR"})
    assert res.status_code in (200, 201)
    data = res.json()
    assert "id" in data
    assert data["code"] == "EXP-0001"


def test_expense_codes_use_transactional_sequence(client, admin_token, db):
    first = client.post("/api/v1/expenses",
        headers=auth(admin_token),
        json={"description": "Taxi", "amount": 20.0,
              "category": "travel", "expense_date": "2025-03-15",
              "currency": "EUR"})
    second = client.post("/api/v1/expenses",
        headers=auth(admin_token),
        json={"description": "Hotel", "amount": 120.0,
              "category": "accommodation", "expense_date": "2025-03-16",
              "currency": "EUR"})

    assert first.status_code in (200, 201)
    assert second.status_code in (200, 201)
    assert first.json()["code"] == "EXP-0001"
    assert second.json()["code"] == "EXP-0002"

    seq = db.query(NumberingSequence).filter(NumberingSequence.entity == "expense").first()
    assert seq is not None
    assert seq.current_value == 2


def test_expense_requires_amount(client, admin_token, db):
    res = client.post("/api/v1/expenses",
        headers=auth(admin_token),
        json={"description": "Sin importe", "category": "travel",
              "expense_date": "2025-03-15"})
    assert res.status_code == 422


def test_update_expense(client, admin_token, db):
    exp_id = client.post("/api/v1/expenses",
        headers=auth(admin_token),
        json={"description": "Gasto editar", "amount": 50.0,
              "category": "meals", "expense_date": "2025-03-10"}
    ).json()["id"]
    res = client.patch(f"/api/v1/expenses/{exp_id}",
        headers=auth(admin_token),
        json={"amount": 65.0, "description": "Gasto editado"})
    assert res.status_code == 200


def test_delete_expense(client, admin_token, db):
    exp_id = client.post("/api/v1/expenses",
        headers=auth(admin_token),
        json={"description": "Gasto borrar", "amount": 10.0,
              "category": "other", "expense_date": "2025-03-01"}
    ).json()["id"]
    res = client.delete(f"/api/v1/expenses/my/{exp_id}", headers=auth(admin_token))
    assert res.status_code == 200
    assert res.json()["ok"] is True

    mine = client.get("/api/v1/expenses/my", headers=auth(admin_token))
    assert mine.status_code == 200
    assert all(e["id"] != exp_id for e in mine.json())

    row = db.query(Expense).filter(Expense.id == exp_id).first()
    assert row is None
