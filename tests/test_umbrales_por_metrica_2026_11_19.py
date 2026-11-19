"""Umbrales de semáforo: una definición por métrica (19-11-2026).

Medido antes: la misma métrica tenía cortes distintos según la pantalla o el
servicio (presupuesto a 70/90, 75/90, 85/100, >80 o >90; SLA a 70/90, 75/90 u
80/95) y servicios que contradecían su propio ajuste (salud de proyecto 70/45
fijo frente a `PROJECT_HEALTH_TRAFFIC_*`, CPI 0,8/0,95 frente a `EVM_INDEX_*`,
riesgo de cambio 75/55/30 frente a `RISK_LEVEL_*`). Ahora `app.core.umbrales`
es la única fuente en el servidor y `/settings/org-defaults` la entrega al
frontend (`useUmbrales()`, `tonoDe`, misma regla).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.core import umbrales as u
from app.core.codigos_de_error import ErrorConCodigo
from app.services import settings_service
from tests.conftest import auth

ORG = "1"


def _poner(db, clave, valor, org=ORG):
    settings_service.set_runtime_value(db, "semaforos", clave, valor, org)


# ── Regla de los cortes (pura) ───────────────────────────────────────────────

@pytest.mark.parametrize("valor,esperado", [(70, "success"), (70.1, "warning"), (90, "warning"), (90.1, "danger")])
def test_mas_es_peor_corta_por_encima_del_umbral(valor, esperado):
    assert u.tono_con("presupuesto", valor, 70, 90) == esperado


@pytest.mark.parametrize("valor,esperado", [(90, "success"), (89.9, "warning"), (75, "warning"), (74.9, "danger")])
def test_menos_es_peor_es_bueno_desde_el_aviso(valor, esperado):
    assert u.tono_con("sla", valor, 90, 75) == esperado


def test_inclusivo_en_riesgo_y_vencimientos():
    assert u.tono_con("riesgo", 75, 50, 75) == "danger"
    assert u.tono_con("riesgo", 50, 50, 75) == "warning"
    assert u.tono_con("vencimiento", 14, 30, 14) == "danger"
    assert u.tono_con("vencimiento", 30, 30, 14) == "warning"
    assert u.tono_con("vencimiento", 31, 30, 14) == "success"


def test_sin_valor_no_hay_tono():
    assert u.tono_de("presupuesto", None) is None


def test_los_valores_por_defecto_son_los_documentados():
    """Los más usados al medirlo (DOCS.md, «Umbrales de semáforo»)."""
    esperados = {
        "presupuesto": (70, 90), "carga": (85, 100), "sla": (90, 75), "okr": (60, 30), "nps": (50, 0),
        "margen": (50, 30), "sprint_completitud": (80, 50), "sprint_velocidad": (85, 50),
        "aprobacion_riesgo_sla": (50, 80), "aprobacion_rechazo": (10, 25), "vencimiento": (30, 14),
        "riesgo": (50, 75), "salud_proyecto": (70, 45), "salud_cliente": (60, 40), "evm": (0.90, 0.85),
    }
    assert set(esperados) == set(u.METRICAS)
    for metrica, cortes in esperados.items():
        assert u.cortes(metrica) == pytest.approx(cortes), metrica


def test_el_frontend_tiene_las_mismas_metricas_y_defectos():
    """utils/umbrales.ts (`UMBRALES_POR_DEFECTO`) espeja `METRICAS` y los defectos de `Settings`."""
    ts = (Path(__file__).resolve().parents[1] / "frontend/src/utils/umbrales.ts").read_text(encoding="utf-8")
    for metrica in u.METRICAS:
        aviso, critico = u.cortes(metrica)
        assert f"  {metrica}: {{ aviso: {aviso:g}, critico: {critico:g}," in ts, metrica
    for clave in u.SUELTOS:
        assert f"    {clave}: {u.umbral(clave):g}," in ts, clave


# ── Por empresa ──────────────────────────────────────────────────────────────

def test_cada_empresa_tiene_sus_umbrales(db):
    _poner(db, "UMBRAL_PRESUPUESTO_CRITICO_PCT", 80)
    assert u.tono_de("presupuesto", 85, db, ORG) == "danger"
    assert u.tono_de("presupuesto", 85, db, "otra-empresa") == "warning"   # sin fila propia: global 70/90


def test_reutiliza_los_ajustes_que_ya_existian(db):
    settings_service.set_runtime_value(db, "health", "PROJECT_HEALTH_TRAFFIC_GREEN", 80, ORG)
    assert u.tono_de("salud_proyecto", 75, db, ORG) == "warning"
    assert u.nivel_de_riesgo(50) == "high" and u.nivel_de_riesgo(25) == "medium" and u.nivel_de_riesgo(10) == "low"


def test_validacion_rango_y_orden(db):
    with pytest.raises(ErrorConCodigo):
        _poner(db, "UMBRAL_PRESUPUESTO_AVISO_PCT", 95)        # aviso > crítico (90)
    with pytest.raises(ErrorConCodigo):
        _poner(db, "UMBRAL_SLA_CRITICO_PCT", 95)              # menos es peor: crítico > aviso (90)
    with pytest.raises(ErrorConCodigo):
        _poner(db, "UMBRAL_NPS_AVISO", 150)                   # fuera de -100..100
    with pytest.raises(ErrorConCodigo):
        _poner(db, "UMBRAL_SOBRECARGA_HORAS_SEMANA", -1)
    _poner(db, "UMBRAL_PRESUPUESTO_AVISO_PCT", 80)
    assert u.cortes("presupuesto", db, ORG) == (80, 90)


def test_estado_de_carga_y_reservas():
    assert u.estado_de_carga(101) == "overloaded"
    assert u.estado_de_carga(90) == "high"
    assert u.estado_de_carga(60) == "ok"
    assert u.estado_de_carga(30) == "under"
    assert u.estado_de_carga(30, libre="free") == "free"


def test_aprobaciones_marcan_el_estado_en_el_servidor():
    from app.services.approval_engine.analytics import _cortes_de_aprobaciones, _marcar_paso
    c = _cortes_de_aprobaciones(None, None)
    paso = {"sla_risk_pct": 60.0, "rejection_rate_pct": 5.0, "pending_count": 1}
    _marcar_paso(paso, c)
    assert (paso["sla_risk_tone"], paso["rejection_tone"], paso["is_critical"]) == ("warning", "success", False)
    paso = {"sla_risk_pct": 10.0, "rejection_rate_pct": 0.0, "pending_count": 3}
    _marcar_paso(paso, c)
    assert paso["is_critical"] is True


def test_el_cpi_usa_evm_index(db):
    from app.services.profitability_service import _bandera_de_riesgo
    assert _bandera_de_riesgo(0.87, 20) == "warning"   # entre EVM_INDEX_RED_BELOW (0,85) y GREEN_MIN (0,90)
    assert _bandera_de_riesgo(0.84, 20) == "critical"  # antes «warning» (corte fijo 0,8)
    assert _bandera_de_riesgo(0.92, 20) == "ok"        # antes «warning» (< 0,95)


def test_burnout_cuenta_semanas_sobre_el_umbral():
    from app.services.ai_modules._base import burnout_score
    assert burnout_score([45, 45, 45, 45], sobrecarga=50) < burnout_score([45, 45, 45, 45], sobrecarga=42)


# ── Al frontend ──────────────────────────────────────────────────────────────

def test_org_defaults_entrega_los_umbrales_a_cualquier_sesion(client, dev_token):
    r = client.get("/api/v1/settings/org-defaults", headers=auth(dev_token))
    assert r.status_code == 200, r.text
    d = r.json()["data"]["umbrales"]
    assert d["presupuesto"] == {"aviso": 70.0, "critico": 90.0, "mayor_peor": True, "inclusivo": False}
    assert d["sueltos"]["UMBRAL_HITOS_HORIZONTE_DIAS"] == 60
