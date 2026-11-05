"""Banco de preguntas validadas de Ask-the-Data (revisión 2026-11)."""
from __future__ import annotations

import pytest

from app.models.ai_chat import AskDataExample
from app.models.mfa import Organization
from app.services import ask_banco
from app.services import ask_the_data as atd
from app.services import settings_service
from tests.conftest import auth
from tests.test_ask_valores_reales_2026_11 import olap  # noqa: F401 — la DuckDB de prueba

URL = "/api/v1/analytics/ask/examples"
SQL_ABIERTOS = "SELECT count(*) AS n FROM fact_tickets WHERE status = 'open'"


@pytest.fixture(autouse=True)
def _cache_limpia():
    settings_service.invalidate_cache()
    yield
    settings_service.invalidate_cache()


def _modelo_prohibido(*a, **k):
    raise AssertionError("no debía llamarse al modelo")


def test_EL_HALLAZGO_la_misma_pregunta_reutiliza_la_consulta_sin_llamar_al_modelo(client, db, olap, admin_token,
                                                                                    monkeypatch):
    r = client.post(URL, json={"question": "¿Cuántos tickets abiertos hay?", "sql": SQL_ABIERTOS},
                    headers=auth(admin_token))
    assert r.status_code == 200
    monkeypatch.setattr(atd, "_generate_sql", _modelo_prohibido)
    res = atd.ask("cuantos tickets ABIERTOS hay", db, org_id="1")       # mayúsculas, sin tilde ni signos
    assert res["rows"] == [{"n": 2}] and res["from_validated_example"]["question"] == "¿Cuántos tickets abiertos hay?"
    assert db.query(AskDataExample).one().times_used == 1


def test_las_parecidas_van_al_modelo_como_ejemplos(db, olap, monkeypatch):
    ask_banco.guardar(db, "1", None, "tickets abiertos por prioridad", SQL_ABIERTOS)
    ask_banco.guardar(db, "1", None, "horas imputadas por proyecto", "SELECT sum(hours) FROM fact_imputations")
    vistos = {}

    def modelo(pregunta, db, **k):
        vistos["ejemplos"] = k.get("ejemplos")
        return "SELECT count(*) AS n FROM fact_tickets WHERE status = 'open' AND priority = 'high'"
    monkeypatch.setattr(atd, "_generate_sql", modelo)
    res = atd.ask("tickets abiertos de prioridad alta", db, org_id="1")
    assert "tickets abiertos por prioridad" in vistos["ejemplos"] and "fact_imputations" not in vistos["ejemplos"]
    assert len(res["examples_used"]) == 1 and res["model_sql"].startswith("SELECT count(*)")


def test_reutilizar_se_puede_apagar(db, olap, monkeypatch):
    ask_banco.guardar(db, "1", None, "tickets abiertos", SQL_ABIERTOS)
    settings_service.set_runtime_value(db, "ai", "ASK_DATA_REUSE_EXACT_EXAMPLE", False, "1")
    db.commit()
    settings_service.invalidate_cache()
    llamadas = []
    monkeypatch.setattr(atd, "_generate_sql", lambda *a, **k: llamadas.append(1) or SQL_ABIERTOS)
    assert "from_validated_example" not in atd.ask("tickets abiertos", db, org_id="1") and llamadas == [1]


def test_otra_empresa_no_ve_ni_usa_los_ejemplos(db, olap, monkeypatch):
    db.add(Organization(id="org-ask", name="Otra", slug="org-ask"))
    db.commit()
    ask_banco.guardar(db, "org-ask", None, "tickets abiertos", SQL_ABIERTOS)
    llamadas = []
    monkeypatch.setattr(atd, "_generate_sql", lambda *a, **k: llamadas.append(k.get("ejemplos")) or SQL_ABIERTOS)
    res = atd.ask("tickets abiertos", db, org_id="1")
    assert "from_validated_example" not in res and llamadas == [""]
    assert ask_banco.lista(db, "1") == []


def test_solo_sql_permitido_y_solo_admin_o_pm(client, db, admin_token, pm_token, dev_token):
    r = client.post(URL, json={"question": "borra todo", "sql": "DELETE FROM fact_tickets WHERE 1=1"},
                    headers=auth(admin_token))
    assert r.status_code == 422
    assert client.post(URL, json={"question": "tickets abiertos", "sql": SQL_ABIERTOS},
                       headers=auth(dev_token)).status_code == 403
    r = client.post(URL, json={"question": "tickets abiertos", "sql": SQL_ABIERTOS}, headers=auth(pm_token))
    assert r.status_code == 200
    lista = client.get(URL, headers=auth(pm_token)).json()["data"]
    assert [e["question"] for e in lista] == ["tickets abiertos"]
    assert client.delete(f"{URL}/{lista[0]['id']}", headers=auth(admin_token)).status_code == 200
    assert client.get(URL, headers=auth(pm_token)).json()["data"] == []
