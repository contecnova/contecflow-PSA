"""Capacidad, reservas, previsión, organigrama, OKR y formación (revisión 2026-11).

Medido antes:
- mover un plan de capacidad no comprobaba sobrecapacidad ni ausencias;
- una reserva `soft` ocupaba capacidad como una firme y los festivos no restaban;
- crear o mover una reserva firme no comprobaba nada;
- hr recibía 403 al mirar la cadena de aprobación de otra persona;
- un KR borrado seguía contando, y cualquiera registraba avance en cualquier KR;
- cualquiera listaba los certificados de toda la empresa.
"""
from __future__ import annotations

from datetime import date, timedelta

from app.models.bookings import ResourceBooking
from app.models.financial import CapacityPlan
from app.models.okrs import KeyResult, Objective
from app.models.settings import Holiday
from app.models.training import Certification
from app.services.okr_service import delete_kr, serialize_objective
from app.services.resource_analytics import get_user_week_hours
from tests.conftest import auth

LUNES = date(2031, 3, 3)  # lejos de cualquier dato sembrado


def test_EL_HALLAZGO_mover_un_plan_comprueba_la_capacidad(client, pm_token, db):
    db.add(CapacityPlan(user_id="dev-test-id", week_start=LUNES + timedelta(days=7), planned_hours=36))
    plan = CapacityPlan(user_id="dev-test-id", week_start=LUNES, planned_hours=10)
    db.add(plan)
    db.commit()
    r = client.patch(f"/api/v1/capacity/plans/{plan.id}", headers=auth(pm_token),
                     json={"week_start": str(LUNES + timedelta(days=7))})
    assert r.status_code == 400, r.text
    # En su misma semana, cambiar las horas no cuenta el propio plan dos veces.
    r = client.patch(f"/api/v1/capacity/plans/{plan.id}", headers=auth(pm_token), json={"planned_hours": 40})
    assert r.status_code == 200, r.text


def test_EL_HALLAZGO_la_tentativa_no_ocupa_y_el_festivo_resta(db):
    db.add_all([
        ResourceBooking(user_id="dev-test-id", booking_type="soft", start_date=LUNES,
                        end_date=LUNES + timedelta(days=4), hours_per_day=8),
        ResourceBooking(user_id="dev-test-id", booking_type="hard", start_date=LUNES,
                        end_date=LUNES, hours_per_day=4),
        Holiday(name="Fiesta", date=LUNES + timedelta(days=2), organization_id="1"),
    ])
    db.commit()
    hw = get_user_week_hours(db, "dev-test-id", LUNES)
    assert hw["committed_hours"] == 4
    assert hw["tentative_hours"] == 40
    assert hw["holiday_hours"] > 0


def test_EL_HALLAZGO_una_reserva_firme_no_pasa_de_la_capacidad(client, pm_token, db):
    cuerpo = {"user_id": "dev-test-id", "start_date": str(LUNES), "end_date": str(LUNES + timedelta(days=4)),
              "hours_per_day": 9, "booking_type": "hard"}
    r = client.post("/api/v1/bookings", headers=auth(pm_token), json=cuerpo)
    assert r.status_code == 400, r.text
    r = client.post("/api/v1/bookings", headers=auth(pm_token), json={**cuerpo, "booking_type": "soft"})
    assert r.status_code == 200, r.text
    r = client.post("/api/v1/bookings", headers=auth(pm_token), json={**cuerpo, "hours_per_day": 8})
    assert r.status_code == 200, r.text
    # Moverla a su propia semana no la cuenta dos veces.
    bid = r.json()["data"]["id"]
    r = client.patch(f"/api/v1/bookings/{bid}", headers=auth(pm_token), json={"hours_per_day": 8})
    assert r.status_code == 200, r.text


def test_EL_HALLAZGO_hr_ve_la_cadena_de_otra_persona(client, hr_token, dev_token, db):
    assert client.get("/api/v1/users/dev-test-id/approval-chain", headers=auth(hr_token)).status_code == 200
    assert client.get("/api/v1/users/pm-test-id/approval-chain", headers=auth(dev_token)).status_code == 403


def _objetivo(db):
    obj = Objective(title="Crecer", year=2031, owner_id="pm-test-id")
    db.add(obj)
    db.flush()
    a = KeyResult(objective_id=obj.id, title="A", target_value=10, current_value=10, owner_id="pm-test-id")
    b = KeyResult(objective_id=obj.id, title="B", target_value=10, current_value=0, owner_id="pm-test-id")
    db.add_all([a, b])
    db.commit()
    return obj, a, b


def test_EL_HALLAZGO_un_kr_borrado_ni_se_ve_ni_cuenta(db):
    obj, _, b = _objetivo(db)
    delete_kr(db, b)
    db.refresh(obj)
    assert [k["title"] for k in serialize_objective(obj)["key_results"]] == ["A"]
    assert obj.progress == 100


def test_EL_HALLAZGO_el_avance_lo_registra_su_responsable(client, dev_token, pm_token, db):
    _, a, _ = _objetivo(db)
    r = client.post(f"/api/v1/okrs/key-results/{a.id}/checkin", headers=auth(dev_token), json={"value": 5})
    assert r.status_code == 403, r.text
    r = client.post(f"/api/v1/okrs/key-results/{a.id}/checkin", headers=auth(pm_token), json={"value": 5})
    assert r.status_code == 201, r.text


def test_EL_HALLAZGO_cada_uno_ve_sus_certificados(client, dev_token, hr_token, db):
    db.add_all([Certification(user_id="pm-test-id", name="PMP"), Certification(user_id="dev-test-id", name="AWS")])
    db.commit()
    propios = client.get("/api/v1/training/certifications", headers=auth(dev_token)).json()["items"]
    assert {c["name"] for c in propios} == {"AWS"}
    ajenos = client.get("/api/v1/training/certifications", headers=auth(dev_token), params={"user_id": "pm-test-id"}).json()["items"]
    assert {c["name"] for c in ajenos} == {"AWS"}
    todos = client.get("/api/v1/training/certifications", headers=auth(hr_token)).json()["items"]
    assert {"PMP", "AWS"} <= {c["name"] for c in todos}
