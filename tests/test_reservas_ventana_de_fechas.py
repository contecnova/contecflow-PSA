"""GET /bookings acepta `date_from`/`date_to`: el planificador pide solo la ventana visible.

El filtro es un solape en SQL: entra toda reserva con `end_date >= date_from`
y `start_date <= date_to`, incluida la que empieza antes de la ventana y la
que la cruza entera. Cada limite es opcional y una fecha mala da 422.
"""
from datetime import date, timedelta

from app.models.bookings import ResourceBooking
from tests.conftest import auth

LUNES = date(2031, 3, 3)  # lejos de cualquier dato de otros tests


def _ids(r):
    assert r.status_code == 200, r.text
    return {b["id"] for b in r.json()["items"]}


def _reserva(db, nombre_dia_ini, nombre_dia_fin, **kw):
    b = ResourceBooking(user_id="dev-test-id", start_date=LUNES + timedelta(days=nombre_dia_ini),
                        end_date=LUNES + timedelta(days=nombre_dia_fin), hours_per_day=4, **kw)
    db.add(b)
    db.flush()
    return b.id


def test_la_ventana_devuelve_las_que_solapan_y_solo_esas(client, admin_token, db):
    antes = _reserva(db, -20, -10)          # acaba antes de la ventana
    entra_por_la_izquierda = _reserva(db, -3, 2)
    dentro = _reserva(db, 5, 6)
    cruza_entera = _reserva(db, -30, 60)
    toca_el_ultimo_dia = _reserva(db, 14, 20)
    despues = _reserva(db, 15, 30)          # empieza justo despues
    borrada = _reserva(db, 5, 6, is_active=False)
    db.commit()

    desde, hasta = LUNES, LUNES + timedelta(days=14)
    r = client.get(f"/api/v1/bookings?date_from={desde}&date_to={hasta}&page_size=1000", headers=auth(admin_token))
    ids = _ids(r)
    assert {entra_por_la_izquierda, dentro, cruza_entera, toca_el_ultimo_dia} <= ids
    assert not ({antes, despues, borrada} & ids)


def test_solo_un_limite_y_sin_limites(client, admin_token, db):
    pasada = _reserva(db, -20, -10)
    futura = _reserva(db, 40, 50)
    db.commit()
    url = "/api/v1/bookings?page_size=1000"
    solo_desde = _ids(client.get(f"{url}&date_from={LUNES}", headers=auth(admin_token)))
    assert futura in solo_desde and pasada not in solo_desde
    solo_hasta = _ids(client.get(f"{url}&date_to={LUNES}", headers=auth(admin_token)))
    assert pasada in solo_hasta and futura not in solo_hasta
    todas = _ids(client.get(url, headers=auth(admin_token)))
    assert {pasada, futura} <= todas


def test_fecha_mala_es_422_y_se_combina_con_otros_filtros(client, admin_token, db):
    mia = _reserva(db, 1, 2)
    db.commit()
    assert client.get("/api/v1/bookings?date_from=ayer", headers=auth(admin_token)).status_code == 422
    r = client.get(f"/api/v1/bookings?date_from={LUNES}&date_to={LUNES + timedelta(days=7)}&user_id=otro-usuario",
                   headers=auth(admin_token))
    assert mia not in _ids(r)
