"""Ask-the-Data: valores reales cuando un filtro no encuentra nada (revisión 2026-11).

Con una DuckDB de verdad (fichero temporal): la consulta, el filtro de empresa y
la lectura de valores corren como en producción; sólo el modelo es un doble.
"""
from __future__ import annotations

import duckdb
import pytest

from app.services import ask_the_data as atd
from app.services import ask_valores_reales as avr
from app.services import settings_service


@pytest.fixture(autouse=True)
def _cache_limpia():
    """Los ajustes en caché sobreviven a la base de cada prueba: se vacían antes y después."""
    settings_service.invalidate_cache()
    yield
    settings_service.invalidate_cache()


@pytest.fixture
def olap(tmp_path, monkeypatch):
    ruta = str(tmp_path / "olap.duckdb")
    c = duckdb.connect(ruta)
    c.execute("CREATE TABLE fact_tickets (ticket_id VARCHAR, organization_id VARCHAR, status VARCHAR, "
              "priority VARCHAR, client_id VARCHAR, satisfaction INT)")
    c.execute("CREATE TABLE dim_client (client_id VARCHAR, name VARCHAR, industry VARCHAR, organization_id VARCHAR)")
    c.executemany("INSERT INTO fact_tickets VALUES (?, ?, ?, ?, ?, ?)", [
        ("t1", "1", "open", "high", "c1", 4), ("t2", "1", "open", "low", "c1", 5),
        ("t3", "1", "closed", "high", "c2", 3),
        ("t9", "otra", "abierto_secreto", "high", "c9", 1),   # de otra empresa: nunca debe aparecer
    ])
    c.executemany("INSERT INTO dim_client VALUES (?, ?, ?, ?)", [
        ("c1", "Acme Industries", "retail", "1"), ("c2", "Globex", "energy", "1"), ("c9", "Secreta SA", "x", "otra")])
    c.close()
    import app.services.olap.etl as etl
    monkeypatch.setattr(etl, "get_duckdb_conn", lambda: duckdb.connect(ruta))
    return ruta


def test_saca_los_filtros_literales_con_su_tabla():
    sql = ("SELECT count(*) FROM fact_tickets t JOIN dim_client c ON c.client_id = t.client_id "
           "WHERE t.status = 'abierto' AND t.priority IN ('alta', 'urgente') AND c.name ILIKE '%acme%' "
           "AND t.satisfaction > 3")
    assert avr.filtros_literales(sql) == [
        {"table": "fact_tickets", "column": "status", "op": "=", "values": ["abierto"]},
        {"table": "fact_tickets", "column": "priority", "op": "in", "values": ["alta", "urgente"]},
        {"table": "dim_client", "column": "name", "op": "like", "values": ["%acme%"]},
    ]
    # Una columna que no está en el esquema publicado no se toca.
    assert avr.filtros_literales("SELECT * FROM fact_tickets WHERE inventada = 'x'") == []


def test_EL_HALLAZGO_un_conteo_a_cero_dice_que_valores_existen_y_solo_de_la_empresa(db, olap, monkeypatch):
    """«¿Cuántos…?» con un valor que no existe devuelve UNA fila con 0, no cero filas."""
    settings_service.set_runtime_value(db, "ai", "ASK_DATA_RETRY_WITH_REAL_VALUES", False, "1")
    db.commit()
    settings_service.invalidate_cache()
    monkeypatch.setattr(atd, "_generate_sql",
                        lambda *a, **k: "SELECT count(*) AS n FROM fact_tickets WHERE status = 'opened'")
    r = atd.ask("¿cuántos tickets abiertos?", db, org_id="1")
    assert r["rows"] == [{"n": 0}]
    (pista,) = r["zero_result_hints"]
    assert pista["searched"] == "opened" and pista["exists"] is False and pista["closest"][0] == "open"
    assert "abierto_secreto" not in pista["sample"] + pista["closest"]


def test_un_conteo_con_resultado_no_lleva_pistas(db, olap, monkeypatch):
    monkeypatch.setattr(atd, "_generate_sql",
                        lambda *a, **k: "SELECT count(*) AS n FROM fact_tickets WHERE status = 'open'")
    r = atd.ask("¿cuántos tickets abiertos?", db, org_id="1")
    assert r["rows"] == [{"n": 2}] and "zero_result_hints" not in r


def test_filas_vacias_con_filtro_y_pistas(db, olap, monkeypatch):
    settings_service.set_runtime_value(db, "ai", "ASK_DATA_RETRY_WITH_REAL_VALUES", False, "1")
    db.commit()
    settings_service.invalidate_cache()
    monkeypatch.setattr(atd, "_generate_sql", lambda *a, **k: "SELECT ticket_id FROM fact_tickets WHERE status = 'opened'")
    r = atd.ask("tickets abiertos", db, org_id="1")
    assert r["row_count"] == 0 and r["error"] is None
    (pista,) = r["zero_result_hints"]
    assert pista == {"table": "fact_tickets", "column": "status", "op": "=", "searched": "opened", "exists": False,
                     "closest": ["open", "closed"], "sample": ["closed", "open"], "distinct_values_read": 2}


def test_reintenta_una_vez_con_los_valores_reales(db, olap, monkeypatch):
    pedidas = []

    def modelo(pregunta, db, **k):
        pedidas.append(k.get("feedback"))
        return ("SELECT ticket_id FROM fact_tickets WHERE status = 'opened'" if len(pedidas) == 1
                else "SELECT ticket_id FROM fact_tickets WHERE status = 'open' ORDER BY ticket_id")
    monkeypatch.setattr(atd, "_generate_sql", modelo)
    r = atd.ask("tickets abiertos", db, org_id="1")
    assert [f["ticket_id"] for f in r["rows"]] == ["t1", "t2"]
    assert r["retried_with_real_values"]["first_sql"].count("opened") == 1
    assert "'opened'" in pedidas[1] and '"open"' in pedidas[1]       # el modelo recibió los valores reales


def test_sin_valor_parecido_no_reintenta(db, olap, monkeypatch):
    pedidas = []
    monkeypatch.setattr(atd, "_generate_sql",
                        lambda *a, **k: pedidas.append(1) or "SELECT ticket_id FROM fact_tickets WHERE status = 'zzzz'")
    r = atd.ask("tickets zzzz", db, org_id="1")
    assert len(pedidas) == 1 and r["zero_result_hints"][0]["closest"] == []
    assert r["zero_result_hints"][0]["sample"] == ["closed", "open"]


def test_like_que_si_existe_no_cuenta_como_falta(db, olap):
    (p,) = avr.pistas("SELECT * FROM dim_client WHERE name ILIKE '%acme%'", "1", max_valores=5, min_parecido=0.5)
    assert p["exists"] is True and p["closest"][0] == "Acme Industries"
