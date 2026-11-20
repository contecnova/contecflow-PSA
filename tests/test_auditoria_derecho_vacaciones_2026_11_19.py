"""El cambio del derecho de vacaciones de una persona queda auditado (19-11-2026, GRC).

`PATCH /advanced-config/vacation-balances/{user_id}` cambiaba los días que le
corresponden a una persona sin dejar rastro. Ahora escribe en `audit_logs`
(recurso `vacation_balance`): quién, de quién, qué año, antes y después; en la
misma transacción que el cambio (si el valor no es válido, ni cambio ni rastro).
"""
from __future__ import annotations

import json

from app.core.config import settings
from app.models.enterprise import AuditLog
from app.models.user import User
from tests.conftest import auth


def _entradas(db):
    return db.query(AuditLog).filter(AuditLog.resource == "vacation_balance").order_by(AuditLog.created_at).all()


def test_cambiar_el_derecho_deja_quien_antes_y_despues(client, db, admin_token):
    dev = db.query(User).filter(User.username == "dev_test").first()
    ruta = f"/api/v1/advanced-config/vacation-balances/{dev.id}"
    r = client.patch(ruta, params={"year": 2031, "days_entitled": 25}, headers=auth(admin_token))
    assert r.status_code == 200, r.text
    r = client.patch(ruta, params={"year": 2031, "days_entitled": 27}, headers=auth(admin_token))
    assert r.status_code == 200, r.text

    entradas = _entradas(db)
    primera = next(e for e in entradas if json.loads(e.new_values)["days_entitled"] == 25.0)
    segunda = next(e for e in entradas if json.loads(e.new_values)["days_entitled"] == 27.0)
    assert primera.action == "UPDATE" and primera.user_id == "admin-test-id"
    assert json.loads(primera.old_values)["days_entitled"] == settings.DEFAULT_VACATION_DAYS_PER_YEAR
    assert json.loads(primera.new_values) == {"days_entitled": 25.0, "year": 2031}
    assert json.loads(primera.metadata_)["fila_nueva"] is True
    assert json.loads(segunda.old_values)["days_entitled"] == 25
    assert json.loads(segunda.new_values)["days_entitled"] == 27.0
    assert json.loads(segunda.metadata_) == {"user_id": dev.id, "fila_nueva": False}
    assert segunda.resource_name == dev.full_name


def test_un_valor_no_valido_no_deja_rastro(client, db, admin_token):
    dev = db.query(User).filter(User.username == "dev_test").first()
    antes = len(_entradas(db))
    r = client.patch(f"/api/v1/advanced-config/vacation-balances/{dev.id}",
                     params={"year": 2026, "days_entitled": 9999}, headers=auth(admin_token))
    assert r.status_code == 422
    assert len(_entradas(db)) == antes
