"""El tiempo de un ticket llega a los partes y a la factura.

Auditoria 2026-11: `billable` se enviaba y no se guardaba, un «dia» eran 8
horas fijas, y el tiempo del ticket no llegaba nunca a los partes del PSA.
"""
from __future__ import annotations

import pytest

from tests.conftest import auth


@pytest.fixture()
def proyecto(db):
    from app.models.project import Project
    p = Project(name="Soporte ACME", code="ACME-SOP", organization_id="1", pm_id="admin-test-id",
                project_type="maintenance", status="active")
    db.add(p)
    db.commit()
    return p


def _ticket(db, **extra):
    from app.models.service_desk import Ticket
    t = Ticket(number="INC-0001", ticket_type="incident", title="Correo caído", description="d",
               organization_id="1", **extra)
    db.add(t)
    db.commit()
    return t


def _log(client, token, t, **datos):
    r = client.post(f"/api/v1/sd/tickets/{t.id}/time-log", headers=auth(token), json=datos)
    assert r.status_code == 200, r.text
    return r.json()["data"]


def test_el_tiempo_facturable_se_guarda_como_facturable(client, admin_token, db):
    from app.models.service_desk import TicketTimeLog
    t = _ticket(db)
    _log(client, admin_token, t, minutes=30, billable=True)
    assert db.query(TicketTimeLog).one().billable is True


def test_sin_proyecto_se_queda_en_el_ticket_y_lo_dice(client, admin_token, db):
    r = _log(client, admin_token, _ticket(db), minutes=60)
    assert r["timesheet"] == "skipped" and "proyecto" in r["reason"]


def test_una_regla_de_los_partes_deja_el_tiempo_en_el_ticket_y_dice_cual(client, admin_token, db, proyecto):
    r = _log(client, admin_token, _ticket(db, project_id=proyecto.id), minutes=60)
    assert r["timesheet"] == "skipped" and "tarifa horaria" in r["reason"]


def test_con_proyecto_llega_a_los_partes_del_agente(client, admin_token, db, proyecto):
    from app.models.imputation import Imputation
    from app.models.service_desk import TicketTimeLog
    from app.models.user import User
    db.get(User, "admin-test-id").hourly_rate = 60.0
    db.commit()
    t = _ticket(db, project_id=proyecto.id)
    r = _log(client, admin_token, t, minutes=90, billable=True, description="Restaurar buzón")
    assert r["timesheet"] == "created", r
    imp = db.query(Imputation).one()
    assert (imp.project_id, imp.hours, imp.is_billable, imp.user_id) == (proyecto.id, 1.5, True, "admin-test-id")
    assert "INC-0001" in imp.description
    assert db.query(TicketTimeLog).one().imputation_id == imp.id


def test_un_dia_son_las_horas_de_la_jornada_configurada(client, admin_token, db):
    from app.models.settings import AppSetting
    from app.services.settings_service import invalidate_cache
    db.add(AppSetting(key="DEFAULT_WORKING_HOURS_PER_DAY", value="7.5", organization_id="1"))
    db.commit()
    invalidate_cache("DEFAULT_WORKING_HOURS_PER_DAY")
    try:
        r = _log(client, admin_token, _ticket(db), minutes=1, unit="days")
    finally:
        invalidate_cache("DEFAULT_WORKING_HOURS_PER_DAY")
    assert r["logged_minutes"] == 450
