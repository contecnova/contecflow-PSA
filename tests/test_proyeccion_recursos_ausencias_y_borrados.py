"""Proyeccion de recursos: sin reservas borradas y con las ausencias restadas.

Auditoria 2026-11: las reservas y planes borrados (borrado logico) seguian
contando, y una semana de vacaciones aprobadas salia como capacidad libre.
"""
from datetime import timedelta

from app.core import timeutil
from app.models.bookings import ResourceBooking
from app.models.resources import Absence
from app.models.user import User
from tests.conftest import auth


def test_semana_con_reserva_borrada_y_vacaciones(client, admin_token, dev_token, db):
    hoy = timeutil.today()
    lunes = hoy - timedelta(days=hoy.weekday()) + timedelta(days=7)
    db.query(User).filter(User.id == "dev-test-id").update({"weekly_capacity_hours": 40})
    db.add_all([
        ResourceBooking(user_id="dev-test-id", start_date=lunes, end_date=lunes + timedelta(days=1),
                        hours_per_day=8),
        ResourceBooking(user_id="dev-test-id", start_date=lunes + timedelta(days=2),
                        end_date=lunes + timedelta(days=4), hours_per_day=8, is_active=False),
        Absence(user_id="dev-test-id", type="vacation", status="approved", start_date=lunes + timedelta(days=2),
                end_date=lunes + timedelta(days=4), working_days=3),
    ])
    db.commit()

    r = client.get(f"/api/v1/resource-forecast/users/dev-test-id?weeks=4&from_date={lunes}", headers=auth(admin_token))
    assert r.status_code == 200, r.text
    semana = r.json()["data"]["weeks"][0]
    # 16 h reservadas; capacidad 40 - 3 dias de vacaciones (8 h) = 16 h.
    assert semana["committed_hours"] == 16
    assert semana["absence_hours"] == 24
    assert semana["load_pct"] == 100
    assert semana["available_hours"] == 0


def test_un_empleado_ve_su_proyeccion_y_no_la_de_otro(client, dev_token):
    assert client.get("/api/v1/resource-forecast/users/dev-test-id", headers=auth(dev_token)).status_code == 200
    assert client.get("/api/v1/resource-forecast/users/admin-test-id", headers=auth(dev_token)).status_code == 403
