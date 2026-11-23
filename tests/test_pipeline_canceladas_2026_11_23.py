"""Oportunidades canceladas en los totales del pipeline (auditoría 04b M9, 23-11-2026).

Regla de mercado (Salesforce/HubSpot), definida en `app/models/pipeline.py`:
  - valor abierto y previsión ponderada: solo etapas abiertas (las perdidas y
    canceladas no suman aunque conserven una probabilidad manual);
  - tasa de éxito = ganadas / (ganadas + perdidas);
  - canceladas («sin decisión»): fuera de la tasa y aparte, con recuento e importe.

Antes: el OLAP (`fact_pipeline`, `NOT is_lost AND NOT is_won`) metía las
canceladas en el embudo y en el pipeline del resumen; las métricas
`forecast_revenue` / `opportunity_by_owner` y el informe de pipeline también;
y `win_rate_evolution` daba siempre 0 (comparaba `str(enum)`).

Datos: abiertas 1000 (10 %) + 2000 (75 %) → valor 3000, ponderado 1600;
ganadas 5000 + 3000; perdida 4000 (40 % manual); cancelada 7000 (50 % manual).
Tasa = 2 / (2 + 1) = 66,7 %.
"""
from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.core import timeutil
from app.models.pipeline import Opportunity, OpportunityStage
from app.services.pipeline_service import resumir_pipeline
from tests.conftest import TestSession, auth

ABIERTO, PONDERADO, CANCELADO, TASA = 3000.0, 1600.0, 7000.0, 66.7

_DATOS = [
    ("lead", 1000, 10), ("negotiation", 2000, 75),
    ("won", 5000, 100), ("won", 3000, 100),
    ("lost", 4000, 40), ("cancelled", 7000, 50),
]


@pytest.fixture
def opps(db):
    for i, (etapa, importe, prob) in enumerate(_DATOS):
        db.add(Opportunity(
            code=f"OPP-M9-{i}", name=f"M9 {i}", client_name="Cliente M9",
            stage=OpportunityStage(etapa), expected_revenue=importe, probability=prob,
            owner_id="admin-test-id", organization_id="1",
        ))
    db.commit()


@pytest.fixture
def sesion_de_prueba(monkeypatch):
    """Los respaldos PostgreSQL del OLAP abren su propia `SessionLocal`."""
    import app.db.session as sesion
    monkeypatch.setattr(sesion, "SessionLocal", TestSession)


def test_resumir_pipeline_puro():
    r = resumir_pipeline([SimpleNamespace(stage=OpportunityStage(e), expected_revenue=v, probability=p)
                          for e, v, p in _DATOS])
    assert (r["open_count"], r["open_value"], r["weighted_value"]) == (2, ABIERTO, PONDERADO)
    assert (r["cancelled_count"], r["cancelled_value"]) == (1, CANCELADO)
    assert (r["won_count"], r["lost_count"], r["win_rate"]) == (2, 1, TASA)
    assert resumir_pipeline([SimpleNamespace(stage="cancelled", expected_revenue=1, probability=0)])["win_rate"] == 0.0


def test_endpoint_kanban_resumen(client, admin_token, opps):
    res = client.get("/api/v1/pipeline/pipeline", headers=auth(admin_token))
    assert res.status_code == 200, res.text
    s = res.json()["data"]["summary"]
    assert s["open_opportunities"] == 2
    assert s["total_pipeline_weighted"] == PONDERADO
    assert s["open_pipeline_value"] == ABIERTO
    assert s["win_rate"] == TASA
    assert (s["cancelled_count"], s["cancelled_value"]) == (1, CANCELADO)
    assert s["won_ytd"] == 8000


def test_respaldo_pg_embudo_y_kpis(db, opps, sesion_de_prueba):
    from app.services.olap import query_engine as qe
    embudo = qe._pg_pipeline_funnel(None)
    assert {f["stage"] for f in embudo} == {"lead", "negotiation"}
    assert sum(f["weighted_revenue"] for f in embudo) == PONDERADO
    k = qe._pg_kpi_summary(None)
    assert k["source"] == "postgresql", k
    assert (k["open_opps"], k["pipeline_weighted"]) == (2, PONDERADO)
    assert (k["cancelled_count"], k["cancelled_value"], k["win_rate"]) == (1, CANCELADO, TASA)


def test_olap_duckdb_embudo_y_kpis(db, opps, tmp_path, monkeypatch):
    pytest.importorskip("duckdb", reason="falta el paquete opcional duckdb (motor OLAP)")
    from app.services.olap import etl, query_engine as qe
    ruta = str(tmp_path / "olap.duckdb")
    monkeypatch.setattr(etl, "DUCKDB_PATH", ruta)
    monkeypatch.setattr(qe, "_DUCKDB_PATH", ruta)
    assert etl.run_full_etl(db)["status"] == "ok"
    embudo = qe.get_pipeline_funnel(None)
    assert {f["stage"] for f in embudo} == {"lead", "negotiation"}  # antes entraba «cancelled»
    k = qe.get_kpi_summary(None)
    assert k["source"] == "olap"
    assert (k["open_opps"], k["pipeline_weighted"]) == (2, PONDERADO)
    assert (k["cancelled_count"], k["cancelled_value"], k["win_rate"]) == (1, CANCELADO, TASA)


def _rango():
    hoy = timeutil.today()
    return hoy - timedelta(days=30), hoy + timedelta(days=1)


def test_metricas_bi(db, opps):
    from app.services.metrics.advanced import _ingreso_de_pipeline
    from app.services.metrics.automations_cmdb import metric_opportunity_by_owner
    from app.services.metrics.business import metric_pipeline_evolution, metric_win_rate_evolution
    d_from, d_to = _rango()
    assert _ingreso_de_pipeline(db, d_from) == PONDERADO
    filas, _ = metric_opportunity_by_owner(db, d_from, d_to, 10)
    assert sum(f["opportunities"] for f in filas) == 2 and sum(f["total_revenue"] for f in filas) == ABIERTO
    filas, _ = metric_win_rate_evolution(db, d_from, d_to, 10)
    assert filas and filas[-1]["value"] == TASA and filas[-1]["cancelled"] == 1
    filas, _ = metric_pipeline_evolution(db, d_from, d_to, 10)
    assert sum(f["value"] for f in filas) == PONDERADO + 8000  # ganadas al 100 %, sin perdidas ni canceladas


def test_informe_de_pipeline(db, opps):
    from app.services.billing_reports.data_source_service import run_pipeline_report
    t = run_pipeline_report(db, {}, None)["totals"]
    assert (t["weighted_amount"], t["open_amount"], t["count"]) == (PONDERADO, ABIERTO, 6)
    assert (t["cancelled_count"], t["cancelled_amount"], t["win_rate"]) == (1, CANCELADO, TASA)
