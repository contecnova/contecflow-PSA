"""Periodo libre en informes (16-11-2026): `app/core/periodo.py`.

Fija el contrato común de todos los informes: `desde`/`hasta` con zona,
granularidad (hour|day|week|month|auto) admitida por informe, los alias
históricos (`days`, `hours`…), los códigos de error traducibles y que la
agrupación en SQLite da la misma clave que en Python (y que en PostgreSQL, que
usa `date_trunc` sobre la hora local).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Column, Date, DateTime, Integer, MetaData, Table, func, select

from app.core.deps import get_current_user, get_db
from app.core.errores import ErrorDeDominio
from app.core.periodo import (
    CON_HORA, SIN_HORA, SOLO_MES, ErrorDePeriodo, LimitesDePeriodo, Periodo,
    clave_de_bucket, expresion_de_bucket, filtro_de_periodo, periodo, resolver_periodo,
)

UTC = timezone.utc
MADRID = ZoneInfo("Europe/Madrid")
AHORA = datetime(2026, 11, 16, 10, 30, tzinfo=UTC)


def _codigo(exc: pytest.ExceptionInfo) -> str:
    return exc.value.detail["code"]


# ── Resolución ────────────────────────────────────────────────────────────────
def test_sin_parametros_usa_los_dias_por_defecto_hasta_ahora():
    p = resolver_periodo(dias_por_defecto=30, ahora=AHORA, zona=UTC)
    assert p.hasta == AHORA and p.desde == AHORA - timedelta(days=30)
    assert p.origen == "defecto"


def test_alias_days_son_los_ultimos_n_dias():
    p = resolver_periodo(dias=7, ahora=AHORA, zona=UTC)
    assert p.duracion == timedelta(days=7) and p.origen == "days"


def test_desde_hasta_sin_zona_se_interpretan_en_la_zona_del_usuario():
    p = resolver_periodo(desde="2026-11-01T00:00", hasta="2026-11-02T00:00", ahora=AHORA, zona=MADRID)
    assert p.desde == datetime(2026, 10, 31, 23, 0, tzinfo=UTC)
    assert p.hasta == datetime(2026, 11, 1, 23, 0, tzinfo=UTC)
    assert p.fecha_desde == date(2026, 11, 1) and p.fecha_hasta == date(2026, 11, 1)


def test_desde_con_desfase_explicito_no_se_reinterpreta():
    p = resolver_periodo(desde="2026-11-01T08:00:00+05:00", hasta="2026-11-01T10:00:00Z", ahora=AHORA, zona=MADRID)
    assert p.desde == datetime(2026, 11, 1, 3, 0, tzinfo=UTC)


def test_desde_tiene_prioridad_sobre_days():
    p = resolver_periodo(desde="2026-11-10", dias=90, ahora=AHORA, zona=UTC)
    assert p.origen == "rango" and p.desde == datetime(2026, 11, 10, tzinfo=UTC) and p.hasta == AHORA


def test_desde_mayor_que_hasta_es_un_error_traducible():
    with pytest.raises(ErrorDePeriodo) as e:
        resolver_periodo(desde="2026-11-10", hasta="2026-11-01", ahora=AHORA, zona=UTC)
    assert _codigo(e) == "periodo.desde_mayor_que_hasta"
    assert isinstance(e.value, ErrorDeDominio) and e.value.status_code == 422


def test_rango_maximo_configurable():
    lim = LimitesDePeriodo(max_dias=10)
    with pytest.raises(ErrorDePeriodo) as e:
        resolver_periodo(dias=11, limites=lim, ahora=AHORA, zona=UTC)
    assert _codigo(e) == "periodo.rango_excedido" and e.value.detail["params"]["maximo"] == 10


def test_fecha_y_zona_invalidas():
    with pytest.raises(ErrorDePeriodo) as e:
        resolver_periodo(desde="ayer", ahora=AHORA, zona=UTC)
    assert _codigo(e) == "periodo.fecha_invalida"
    with pytest.raises(ErrorDePeriodo) as e:
        resolver_periodo(tz="Marte/Olympus", ahora=AHORA)
    assert _codigo(e) == "periodo.zona_invalida"


# ── Granularidad ──────────────────────────────────────────────────────────────
def test_hora_rechazada_si_el_dato_es_por_dia():
    with pytest.raises(ErrorDePeriodo) as e:
        resolver_periodo(dias=7, granularidad="hour", admitidas=SIN_HORA, ahora=AHORA, zona=UTC)
    assert _codigo(e) == "periodo.hora_no_admitida"


def test_semana_rechazada_si_el_dato_es_mensual():
    with pytest.raises(ErrorDePeriodo) as e:
        resolver_periodo(dias=90, granularidad="week", admitidas=SOLO_MES, ahora=AHORA, zona=UTC)
    assert _codigo(e) == "periodo.granularidad_no_admitida"


def test_granularidad_desconocida():
    with pytest.raises(ErrorDePeriodo) as e:
        resolver_periodo(dias=7, granularidad="minute", ahora=AHORA, zona=UTC)
    assert _codigo(e) == "periodo.granularidad_invalida"


def test_auto_elige_la_mas_fina_dentro_del_objetivo():
    lim = LimitesDePeriodo(auto_max_puntos=120)
    assert resolver_periodo(dias=1, limites=lim, ahora=AHORA, zona=UTC).granularidad == "hour"
    assert resolver_periodo(dias=30, limites=lim, ahora=AHORA, zona=UTC).granularidad == "day"
    assert resolver_periodo(dias=365, limites=lim, ahora=AHORA, zona=UTC).granularidad == "week"
    assert resolver_periodo(dias=1800, limites=lim, ahora=AHORA, zona=UTC).granularidad == "month"
    assert resolver_periodo(dias=1, admitidas=SIN_HORA, limites=lim, ahora=AHORA, zona=UTC).granularidad == "day"


def test_maximo_de_puntos_por_granularidad():
    lim = LimitesDePeriodo(max_puntos={"hour": 48, "day": 1000, "week": 500, "month": 200})
    with pytest.raises(ErrorDePeriodo) as e:
        resolver_periodo(dias=3, granularidad="hour", limites=lim, ahora=AHORA, zona=UTC)
    assert _codigo(e) == "periodo.demasiados_puntos" and e.value.detail["params"]["maximo"] == 48
    # sin serie (KPI) no se cuentan puntos
    assert resolver_periodo(dias=3, granularidad="hour", limites=lim, serie=False, ahora=AHORA, zona=UTC)


def test_comparar_solo_si_el_informe_lo_soporta_y_anterior_de_igual_duracion():
    p = resolver_periodo(dias=7, comparar=True, comparable=True, ahora=AHORA, zona=UTC)
    assert p.comparar
    a = p.anterior()
    assert a.hasta == p.desde and a.duracion == p.duracion
    assert not resolver_periodo(dias=7, comparar=True, comparable=False, ahora=AHORA, zona=UTC).comparar


def test_sentido_futuro_para_horizontes():
    p = resolver_periodo(dias=90, sentido="futuro", ahora=AHORA, zona=UTC)
    assert p.desde == AHORA and p.hasta == AHORA + timedelta(days=90)


# ── Tramos ────────────────────────────────────────────────────────────────────
def test_claves_de_tramo_en_la_zona():
    # 23:30 UTC del 1 de noviembre es el día 2 en Madrid (UTC+1)
    i = datetime(2026, 11, 1, 23, 30, tzinfo=UTC)
    assert clave_de_bucket(i, MADRID, "hour") == "2026-11-02T00:00"
    assert clave_de_bucket(i, MADRID, "day") == "2026-11-02T00:00"
    assert clave_de_bucket(i, MADRID, "week") == "2026-11-02T00:00"  # lunes
    assert clave_de_bucket(i, MADRID, "month") == "2026-11-01T00:00"
    # sin zona = UTC almacenado; una fecha pura no se mueve de día
    assert clave_de_bucket(datetime(2026, 11, 1, 23, 30), MADRID, "day") == "2026-11-02T00:00"
    assert clave_de_bucket(date(2026, 11, 4), MADRID, "week") == "2026-11-02T00:00"
    assert clave_de_bucket("2026-11-01 23:30:00.000000", MADRID, "day") == "2026-11-02T00:00"


def test_rellenar_huecos_con_ceros_e_instante_iso():
    p = resolver_periodo(desde="2026-11-01", hasta="2026-11-04", granularidad="day", ahora=AHORA, zona=MADRID)
    serie = p.rellenar({"2026-11-02T00:00": 5})
    assert [s["clave"] for s in serie] == ["2026-11-01T00:00", "2026-11-02T00:00", "2026-11-03T00:00"]
    assert [s["valor"] for s in serie] == [0, 5, 0]
    assert serie[0]["t"] == "2026-11-01T00:00:00+01:00"
    multi = p.rellenar({"2026-11-01T00:00": {"a": 1, "b": 2}}, vacio={"a": 0, "b": 0})
    assert multi[1] == {"t": "2026-11-02T00:00:00+01:00", "clave": "2026-11-02T00:00", "a": 0, "b": 0}


def test_cambio_de_hora_no_duplica_tramos():
    # 25-10-2026: en Madrid las 03:00 vuelven a ser las 02:00
    p = resolver_periodo(desde="2026-10-25T00:00:00Z", hasta="2026-10-25T04:00:00Z", granularidad="hour", ahora=AHORA, zona=MADRID)
    claves = p.claves()
    assert len(claves) == len(set(claves))


def test_agrupar_en_memoria_filtra_y_suma():
    p = resolver_periodo(desde="2026-11-01", hasta="2026-11-03", granularidad="day", ahora=AHORA, zona=UTC)
    filas = [SimpleNamespace(t=datetime(2026, 11, 1, 5), v=2), SimpleNamespace(t=datetime(2026, 11, 1, 6), v=3),
             SimpleNamespace(t=datetime(2026, 11, 5, 6), v=100)]
    assert p.agrupar(filas, lambda f: f.t, lambda f: f.v) == {"2026-11-01T00:00": 5}


def test_agrupacion_sqlite_identica_a_python(db):
    meta = MetaData()
    tabla = Table("periodo_prueba", meta, Column("id", Integer, primary_key=True),
                  Column("en", DateTime(timezone=True)), Column("dia", Date))
    meta.create_all(db.get_bind())
    try:
        instantes = [datetime(2026, 11, 1, 22, 59), datetime(2026, 11, 1, 23, 1), datetime(2026, 11, 2, 9, 0),
                     datetime(2026, 11, 9, 9, 0)]
        db.execute(tabla.insert(), [{"en": i, "dia": i.date()} for i in instantes])
        for gran in ("hour", "day", "week", "month"):
            p = resolver_periodo(desde="2026-10-01", hasta="2026-12-01", granularidad=gran,
                                 ahora=AHORA, zona=MADRID)
            b = expresion_de_bucket(db, tabla.c.en, p).label("k")
            filas = db.execute(select(b, func.count()).where(filtro_de_periodo(tabla.c.en, p)).group_by(b)).all()
            esperado: dict = {}
            for i in instantes:
                k = clave_de_bucket(i, MADRID, gran)
                esperado[k] = esperado.get(k, 0) + 1
            assert dict(filas) == esperado, gran
        p = resolver_periodo(desde="2026-10-01", hasta="2026-12-01", granularidad="week", admitidas=SIN_HORA,
                             ahora=AHORA, zona=MADRID)
        b = expresion_de_bucket(db, tabla.c.dia, p).label("k")
        filas = dict(db.execute(select(b, func.count()).group_by(b)).all())
        assert filas == {"2026-10-26T00:00": 1, "2026-11-02T00:00": 2, "2026-11-09T00:00": 1}
    finally:
        meta.drop_all(db.get_bind())


# ── Dependencia FastAPI y alias ──────────────────────────────────────────────
def _app():
    from fastapi.responses import JSONResponse

    app = FastAPI()

    @app.exception_handler(ErrorDeDominio)
    async def _h(_r, exc):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.get("/dia")
    def por_dia(p: Periodo = Depends(periodo(dias_por_defecto=30, granularidades=SIN_HORA, alias_dias=("days", "lookback_days")))):
        return p.a_dict()

    @app.get("/hora")
    def por_hora(p: Periodo = Depends(periodo(dias_por_defecto=1, granularidades=CON_HORA, alias_dias=(), alias_horas=("hours",)))):
        return p.a_dict()

    @app.get("/legado")
    def legado(p: Periodo = Depends(periodo(granularidades=SIN_HORA, alias_desde=("start_date",), alias_hasta=("end_date",),
                                            alias_granularidad="period"))):
        return p.a_dict()

    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(organization_id=None)
    app.dependency_overrides[get_db] = lambda: None
    return app


@pytest.fixture()
def cliente(monkeypatch):
    import app.core.periodo as mod
    monkeypatch.setattr(mod, "limites_de_periodo", lambda _db, _org=None: LimitesDePeriodo())
    return TestClient(_app())


def test_dependencia_alias_days_y_alias_propio(cliente):
    a = cliente.get("/dia", params={"days": 7}).json()
    b = cliente.get("/dia", params={"lookback_days": 7}).json()
    for r in (a, b):
        d = datetime.fromisoformat(r["hasta"]) - datetime.fromisoformat(r["desde"])
        assert d == timedelta(days=7) and r["origen"] == "days"


def test_dependencia_alias_horas(cliente):
    r = cliente.get("/hora", params={"hours": 6}).json()
    assert datetime.fromisoformat(r["hasta"]) - datetime.fromisoformat(r["desde"]) == timedelta(hours=6)
    assert r["granularidad"] == "hour"


def test_dependencia_desde_hasta_tz_y_granularidad(cliente):
    r = cliente.get("/hora", params={"desde": "2026-11-01T08:00", "hasta": "2026-11-01T20:00",
                                     "tz": "Europe/Madrid", "granularidad": "hour"}).json()
    assert r["desde"] == "2026-11-01T07:00:00+00:00" and r["zona"] == "Europe/Madrid"


def test_dependencia_rechaza_hora_con_codigo(cliente):
    r = cliente.get("/dia", params={"days": 7, "granularidad": "hour"})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "periodo.hora_no_admitida"


def test_dependencia_alias_de_fechas_inclusivas_y_granularidad_legada(cliente):
    r = cliente.get("/legado", params={"start_date": "2026-11-01", "end_date": "2026-11-30", "period": "weekly",
                                       "tz": "UTC"}).json()
    assert r["desde"].startswith("2026-11-01T00:00") and r["hasta"].startswith("2026-12-01T00:00")
    assert r["granularidad"] == "week"


def test_endpoint_de_limites_lee_los_ajustes_en_caliente(client, admin_token):
    from tests.conftest import auth

    r = client.get("/api/v1/periodo/limites", headers=auth(admin_token))
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["max_dias"] > 0 and set(d["max_puntos"]) == {"hour", "day", "week", "month"}
    assert d["granularidades"] == ["hour", "day", "week", "month"]


def test_alias_con_nombre_reservado_y_horizonte_de_hoy(monkeypatch):
    """`from`/`to` (palabras reservadas) valen como alias; `days=0` en un horizonte es «solo hoy»."""
    import app.core.periodo as mod
    from fastapi.responses import JSONResponse

    monkeypatch.setattr(mod, "limites_de_periodo", lambda _db, _org=None: LimitesDePeriodo())
    app = FastAPI()

    @app.exception_handler(ErrorDeDominio)
    async def _h(_r, exc):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.get("/reservado")
    def reservado(p: Periodo = Depends(periodo(granularidades=SIN_HORA, alias_desde=("from",), alias_hasta=("to",)))):
        return p.a_dict()

    @app.get("/futuro")
    def futuro(p: Periodo = Depends(periodo(granularidades=SIN_HORA, sentido="futuro", serie=False))):
        return p.a_dict()

    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(organization_id=None)
    app.dependency_overrides[get_db] = lambda: None
    c = TestClient(app)
    r = c.get("/reservado", params={"from": "2026-11-01", "to": "2026-11-30", "tz": "UTC"}).json()
    assert r["desde"].startswith("2026-11-01") and r["hasta"].startswith("2026-12-01")
    r = c.get("/futuro", params={"days": 0, "tz": "UTC"})
    assert r.status_code == 200
    d = r.json()
    assert datetime.fromisoformat(d["hasta"]) > datetime.fromisoformat(d["desde"])
