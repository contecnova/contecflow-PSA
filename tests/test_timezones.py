"""Zonas horarias: los bordes de día ya no los decide el servidor (P2-14).

El caso que fallaba: un empleado en México (UTC-6) imputa a las 23:30 del día 28.
El servidor corre en UTC, donde ya son las 05:30 del día 29, así que
`date.today()` devolvía el 29. Su día 28 quedaba vacío y el 29 con horas que no
trabajó ese día.

`Imputation.date` es un `Date` puro —un día de calendario, sin instante—, así que
«qué día es hoy» no tiene una respuesta única: depende de para quién. De ahí las
dos cadenas de resolución, que responden preguntas distintas:

  · «¿qué día es hoy para esta persona?»   → usuario → organización → UTC
  · «¿qué abarca el periodo de facturación?» → cliente → organización → UTC
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.core.timeutil import (
    UTC,
    as_utc,
    day_bounds_in,
    month_bounds_in,
    period_bounds_for_client,
    resolve_zone,
    today_in,
    zone_for_client,
    zone_for_user,
)


class _Zonificable:
    """Doble mínimo: sólo hace falta el atributo `timezone`."""

    def __init__(self, timezone=None):
        self.timezone = timezone


# ── Resolución de zonas ───────────────────────────────────────────────────────

def test_resolve_zone_acepta_un_nombre_valido():
    assert resolve_zone("Europe/Madrid") is not None
    assert str(resolve_zone("Europe/Madrid")) == "Europe/Madrid"


@pytest.mark.parametrize("entrada", [None, "", "No/Existe", "basura", 123])
def test_una_zona_invalida_degrada_a_utc_sin_lanzar(entrada):
    """Una zona mal escrita en la ficha de un cliente no debe tumbar la petición.

    Degradar a UTC preserva el comportamiento anterior; lanzar convertiría un
    dato mal introducido en una caída.
    """
    assert resolve_zone(entrada) is UTC


# ── Cadena del usuario ────────────────────────────────────────────────────────

def test_la_zona_del_usuario_manda_sobre_la_de_la_organizacion():
    usuario = _Zonificable("America/Mexico_City")
    org = _Zonificable("Europe/Madrid")
    assert str(zone_for_user(usuario, org)) == "America/Mexico_City"


def test_sin_zona_de_usuario_se_hereda_la_de_la_organizacion():
    assert str(zone_for_user(_Zonificable(None), _Zonificable("Europe/Madrid"))) == "Europe/Madrid"


def test_sin_ninguna_zona_la_cadena_del_usuario_acaba_en_utc():
    assert zone_for_user(_Zonificable(None), _Zonificable(None)) is UTC
    assert zone_for_user(None, None) is UTC


# ── Cadena del cliente ────────────────────────────────────────────────────────

def test_la_zona_del_cliente_manda_sobre_la_de_la_organizacion():
    cliente = _Zonificable("America/New_York")
    org = _Zonificable("Europe/Madrid")
    assert str(zone_for_client(cliente, org)) == "America/New_York"


def test_sin_zona_de_cliente_se_hereda_la_de_la_organizacion():
    """NULL en clients.timezone = comportamiento anterior, sin sorpresas."""
    assert str(zone_for_client(_Zonificable(None), _Zonificable("Europe/Madrid"))) == "Europe/Madrid"


def test_el_modelo_client_tiene_columna_timezone():
    """No existía: era el dato que faltaba para poder cortar por cliente."""
    from app.models.clients import Client

    assert "timezone" in Client.__table__.columns, (
        "clients.timezone no existe; los cortes por cliente no pueden funcionar"
    )
    assert Client.__table__.columns["timezone"].nullable, (
        "debe admitir NULL = heredar de la organización"
    )


# ── El bug concreto ───────────────────────────────────────────────────────────

def test_el_dia_depende_de_la_zona():
    """Demuestra el desfase que producía `date.today()`.

    A las 05:30 UTC del día 29 todavía es el día 28 en México. El empleado que
    imputó a sus 23:30 del 28 debe ver el 28.
    """
    instante = datetime(2026, 8, 29, 5, 30, tzinfo=UTC)
    mexico = resolve_zone("America/Mexico_City")

    assert instante.date() == date(2026, 8, 29)            # lo que veía el servidor
    assert instante.astimezone(mexico).date() == date(2026, 8, 28)  # el día real


def test_today_in_devuelve_un_dia_de_calendario():
    hoy_utc = today_in(UTC)
    hoy_madrid = today_in(resolve_zone("Europe/Madrid"))
    assert isinstance(hoy_utc, date) and isinstance(hoy_madrid, date)
    # Como mucho difieren en un día, según la hora a la que corra el test.
    assert abs((hoy_madrid - hoy_utc).days) <= 1


# ── Cortes de día ─────────────────────────────────────────────────────────────

def test_los_limites_de_dia_son_semiabiertos():
    """[inicio, fin) — el fin es EXCLUSIVO a propósito.

    Con un fin inclusivo habría que elegir un último instante representable
    (23:59:59) y se perdería lo ocurrido en el último segundo. Con intervalo
    semiabierto no hay huecos ni solapes entre días consecutivos.
    """
    zona = resolve_zone("America/Mexico_City")
    inicio, fin = day_bounds_in(date(2026, 8, 28), zona)
    assert inicio == datetime(2026, 8, 28, 6, 0, tzinfo=UTC)   # UTC-6
    assert fin == datetime(2026, 8, 29, 6, 0, tzinfo=UTC)
    # El fin de un día es exactamente el inicio del siguiente: sin huecos.
    inicio_siguiente, _ = day_bounds_in(date(2026, 8, 29), zona)
    assert fin == inicio_siguiente


# ── Cortes de mes: el cierre de facturación ───────────────────────────────────

def test_el_mes_se_corta_en_la_zona_indicada():
    """El caso del cierre mensual de una organización en Madrid.

    Con corte en UTC se perdía la primera hora del 1 de agosto y se colaba la
    primera hora del 1 de septiembre.
    """
    inicio, fin = month_bounds_in(2026, 8, resolve_zone("Europe/Madrid"))
    assert inicio == datetime(2026, 7, 31, 22, 0, tzinfo=UTC)  # UTC+2 en verano
    assert fin == datetime(2026, 8, 31, 22, 0, tzinfo=UTC)


def test_diciembre_cruza_bien_el_año():
    inicio, fin = month_bounds_in(2026, 12, UTC)
    assert inicio == datetime(2026, 12, 1, tzinfo=UTC)
    assert fin == datetime(2027, 1, 1, tzinfo=UTC)


@pytest.mark.parametrize("mes", [0, 13, -1])
def test_un_mes_fuera_de_rango_se_rechaza(mes):
    with pytest.raises(ValueError):
        month_bounds_in(2026, mes, UTC)


def test_el_periodo_del_cliente_usa_su_zona():
    """Punto de entrada de los cierres: encapsula la cadena de resolución."""
    cliente = _Zonificable("America/New_York")
    org = _Zonificable("Europe/Madrid")
    inicio, _ = period_bounds_for_client(2026, 8, cliente, org)
    # Nueva York en agosto es UTC-4: el mes empieza a las 04:00 UTC del día 1.
    assert inicio == datetime(2026, 8, 1, 4, 0, tzinfo=UTC)


def test_el_periodo_cae_a_la_organizacion_si_el_cliente_no_tiene_zona():
    inicio, _ = period_bounds_for_client(2026, 8, _Zonificable(None), _Zonificable("Europe/Madrid"))
    assert inicio == datetime(2026, 7, 31, 22, 0, tzinfo=UTC)


# ── Horario de verano ─────────────────────────────────────────────────────────

def test_el_cambio_de_hora_no_produce_dias_de_24h_fijas():
    """El día del cambio de hora tiene 23 o 25 horas, no 24.

    Un cálculo que asuma 24 h fijas descuadra las horas imputadas ese día. En
    España el reloj se adelanta el último domingo de marzo.
    """
    zona = resolve_zone("Europe/Madrid")
    inicio, fin = day_bounds_in(date(2026, 3, 29), zona)  # adelanto de hora
    horas = (fin - inicio).total_seconds() / 3600
    assert horas == 23, f"el día del adelanto debe tener 23 h, calculadas {horas}"

    inicio_o, fin_o = day_bounds_in(date(2026, 10, 25), zona)  # atraso de hora
    horas_o = (fin_o - inicio_o).total_seconds() / 3600
    assert horas_o == 25, f"el día del atraso debe tener 25 h, calculadas {horas_o}"


# ── Los datos ya almacenados ──────────────────────────────────────────────────

def test_un_datetime_sin_zona_se_interpreta_como_utc():
    """Comprobado antes de tocar nada: los timestamps almacenados SON UTC.

    De las escrituras a columnas de fecha-hora, 139 usan `utcnow()`, 374
    `datetime.now(timezone.utc)` y 437 `func.now()` sobre columnas con zona.
    Interpretarlos como hora local del servidor los desplazaría por el offset y
    corrompería el histórico, así que NO hay migración de desplazamiento.
    """
    naive = datetime(2026, 8, 28, 12, 0)
    assert as_utc(naive) == datetime(2026, 8, 28, 12, 0, tzinfo=UTC)


def test_un_datetime_con_zona_se_convierte_sin_mover_el_instante():
    con_zona = datetime(2026, 8, 28, 14, 0, tzinfo=timezone(offset=__import__("datetime").timedelta(hours=2)))
    assert as_utc(con_zona) == datetime(2026, 8, 28, 12, 0, tzinfo=UTC)


def test_utcnow_sigue_devolviendo_utc_sin_zona():
    """139 puntos del código lo usan y su contrato es correcto."""
    from app.core.timeutil import utcnow, utcnow_aware

    n = utcnow()
    assert n.tzinfo is None
    assert utcnow_aware().tzinfo is UTC
    # Ambos representan el mismo instante.
    assert abs((utcnow_aware().replace(tzinfo=None) - n).total_seconds()) < 5
