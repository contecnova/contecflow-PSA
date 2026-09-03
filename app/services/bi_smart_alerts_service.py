"""BI Smart Alerts service.

Intelligent alert rules that go beyond simple thresholds:
- Trend-based alerts (sustained rise/drop over N periods)
- Anomaly-escalation alerts (z-score based)
- Cross-metric correlation alerts (if A triggers → check B)
- Alert fatigue reduction (cooldown windows)
- Alert history + acknowledgment

State is persisted in AppSetting JSON, scoped by organization.

This module is the public façade. The implementation is split into cohesive
submodules under ``app.services.bi_smart_alerts`` (constants, persistence,
rule/custom-metric/log CRUD, statistics and metric extraction). Everything is
re-exported here so the historical import path and public API are preserved
exactly. ``evaluate_alerts`` stays defined in this module on purpose: tests and
callers monkeypatch ``_fetch_metric_series`` on this module, and keeping the
orchestration here ensures that patch is honoured.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.settings import AppSetting
from app.models.user import User

from app.services.bi_smart_alerts.constants import (
    CUSTOM_METRICS_KEY,
    LOG_KEY,
    RULES_KEY,
    SUPPORTED_CONDITIONS,
    SUPPORTED_METRICS,
)
from app.services.bi_smart_alerts.custom_metrics import (
    create_custom_metric,
    delete_custom_metric,
    list_custom_metrics,
)
from app.services.bi_smart_alerts.log import acknowledge_alert, get_alert_log
from app.services.bi_smart_alerts.metrics import _fetch_metric_series
from app.services.bi_smart_alerts.persistence import (
    _get_json,
    _iso_now,
    _set_json,
    _setting_row,
)
from app.services.bi_smart_alerts.rules import (
    create_alert_rule,
    delete_alert_rule,
    list_alert_rules,
    update_alert_rule,
)
from app.services.bi_smart_alerts.statistics import (
    _historical_anomaly,
    _is_cooldown_active,
    _pearson_corr,
    _z_score,
)

logger = logging.getLogger(__name__)

# Names re-exported for the historical public API. Listing them in ``__all__``
# both documents the façade and marks the re-export imports above as intentional.
__all__ = [
    "json",
    "datetime",
    "timezone",
    "AppSetting",
    "User",
    "RULES_KEY",
    "LOG_KEY",
    "CUSTOM_METRICS_KEY",
    "SUPPORTED_METRICS",
    "SUPPORTED_CONDITIONS",
    "_iso_now",
    "_setting_row",
    "_get_json",
    "_set_json",
    "list_alert_rules",
    "create_alert_rule",
    "update_alert_rule",
    "delete_alert_rule",
    "list_custom_metrics",
    "create_custom_metric",
    "delete_custom_metric",
    "get_alert_log",
    "acknowledge_alert",
    "_z_score",
    "_pearson_corr",
    "_historical_anomaly",
    "_is_cooldown_active",
    "_fetch_metric_series",
    "evaluate_alerts",
    "default_alert_rules",
    "seed_default_rules_if_empty",
]


# ── Alert evaluation engine ────────────────────────────────────────────────────

# ── Evaluación de alertas inteligentes ───────────────────────────────────────
#
# Auditoria 2026-08 (hallazgo 18). `evaluate_alerts` era complejidad 17: cinco
# condiciones en cadena de `elif` mas la comprobacion de metricas correladas,
# todo dentro del bucle de reglas.
#
# `trend_up` y `trend_down` eran el mismo bloque con el operador invertido, y la
# tabla lo hace explicito.


# Correlacion minima para considerar que dos metricas se mueven juntas. 0,55 es
# una correlacion moderada: por debajo, la coincidencia puede ser casualidad de
# doce puntos de serie.
_CORRELACION_MINIMA = 0.55

# Cuantos periodos se cruzan al medir correlacion. Doce es un ano de meses.
_PERIODOS_DE_CORRELACION = 12

# Tope del registro de alertas. Sin el, el JSON crece sin limite en una columna
# de texto.
_MAX_ENTRADAS_DE_REGISTRO = 500


def _cond_por_encima(valores: list, actual: float, umbral, periodos: int) -> tuple:
    if umbral is None or not actual > umbral:
        return False, {}
    return True, {"threshold": umbral}


def _cond_por_debajo(valores: list, actual: float, umbral, periodos: int) -> tuple:
    if umbral is None or not actual < umbral:
        return False, {}
    return True, {"threshold": umbral}


def _monotona(ventana: list, creciente: bool) -> bool:
    """Si la ventana sube (o baja) en todos sus tramos, sin empates.

    Estricta a proposito: una serie que se queda plana un mes no es una
    tendencia, y avisar de ella llenaria el panel de ruido.
    """
    if creciente:
        return all(ventana[i] < ventana[i + 1] for i in range(len(ventana) - 1))
    return all(ventana[i] > ventana[i + 1] for i in range(len(ventana) - 1))


def _cond_tendencia(creciente: bool):
    """Construye la condicion de tendencia. Las dos eran el mismo bloque."""
    def evaluar(valores: list, actual: float, umbral, periodos: int) -> tuple:
        ventana = valores[-periodos:]
        if len(ventana) < 2:
            # Con un solo punto no hay tendencia que medir.
            return False, {}
        return _monotona(ventana, creciente), {"trend_window": ventana}
    return evaluar


def _cond_anomalia(valores: list, actual: float, umbral, periodos: int) -> tuple:
    evaluacion = _historical_anomaly(valores)
    return bool(evaluacion["is_anomaly"]), evaluacion


# Las cinco condiciones que puede usar una regla. Una condicion desconocida no
# dispara: la regla queda inerte en vez de avisar sin motivo.
_CONDICIONES = {
    "threshold_above": _cond_por_encima,
    "threshold_below": _cond_por_debajo,
    "trend_up": _cond_tendencia(creciente=True),
    "trend_down": _cond_tendencia(creciente=False),
    "anomaly": _cond_anomalia,
}

CONDICIONES_SOPORTADAS = frozenset(_CONDICIONES)


def _evaluar_condicion_de_regla(rule: dict, valores: list) -> tuple:
    """Decide si la regla dispara. Devuelve (dispara, detalle)."""
    actual = valores[-1]
    detalle = {"current_value": actual, "metric_key": rule.get("metric_key", "")}

    evaluar = _CONDICIONES.get(rule.get("condition", ""))
    if evaluar is None:
        return False, detalle

    dispara, extra = evaluar(
        valores, actual, rule.get("threshold"),
        max(2, int(rule.get("trend_periods", 3))),
    )
    detalle.update(extra)
    return dispara, detalle


def _metricas_correladas_que_confirman(db: Session, organization_id, rule: dict,
                                       valores: list) -> list:
    """Las metricas correladas que tambien estan anomalas y en el mismo sentido.

    Sirven de confirmacion: una metrica que se sale sola puede ser un dato raro,
    pero dos que se mueven juntas y las dos se salen a la vez es una senal. Se
    exige correlacion, anomalia Y que las dos vayan en la misma direccion — sin
    lo ultimo, dos metricas inversamente correladas se confirmarian entre si al
    moverse en sentidos opuestos, que es precisamente lo normal en ellas.
    """
    actual = valores[-1]
    hits = []
    for corr_metric in (rule.get("correlated_metrics") or []):
        corr_values = _fetch_metric_series(db, corr_metric, organization_id)
        if not corr_values:
            continue
        size = min(len(valores), len(corr_values), _PERIODOS_DE_CORRELACION)
        corr_coeff = _pearson_corr(valores[-size:], corr_values[-size:])
        corr_anomaly = _historical_anomaly(corr_values)
        variacion = actual - valores[-2] if len(valores) >= 2 else 0.0
        variacion_corr = (
            corr_values[-1] - corr_values[-2] if len(corr_values) >= 2 else 0.0
        )
        mismo_sentido = (
            (variacion >= 0 and variacion_corr >= 0)
            or (variacion <= 0 and variacion_corr <= 0)
        )
        if (abs(corr_coeff) >= _CORRELACION_MINIMA
                and bool(corr_anomaly["is_anomaly"]) and mismo_sentido):
            hits.append({
                "metric_key": corr_metric,
                "current_value": round(float(corr_values[-1]), 3),
                "corr_coef": round(float(corr_coeff), 3),
                "z_score": corr_anomaly["z_score"],
                "robust_z": corr_anomaly["robust_z"],
            })
    return hits


def _entrada_de_alerta(rule: dict, detalle: dict, correlated_hits: list) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "rule_id": rule["id"],
        "rule_name": rule.get("name", ""),
        "metric_key": rule.get("metric_key", ""),
        "condition": rule.get("condition", ""),
        "severity": rule.get("severity", "warning"),
        "detail": detalle,
        "correlated": correlated_hits,
        "triggered_at": _iso_now(),
        "acknowledged": False,
        "acknowledged_by": None,
        "acknowledged_at": None,
    }


def _alerta_de_la_regla(db: Session, organization_id, rule: dict) -> Optional[dict]:
    """La alerta que dispara esta regla, o None si no dispara."""
    if not rule.get("enabled", True):
        return None
    if _is_cooldown_active(rule):
        # El periodo de silencio evita que una metrica que sigue mal avise cada
        # vez que se evalua.
        return None

    valores = _fetch_metric_series(db, rule.get("metric_key", ""), organization_id)
    if not valores:
        return None

    dispara, detalle = _evaluar_condicion_de_regla(rule, valores)
    if not dispara:
        return None

    correlated_hits = _metricas_correladas_que_confirman(
        db, organization_id, rule, valores
    )
    # Si la regla PIDE confirmacion por correlacion y no la obtiene, no avisa.
    if rule.get("correlated_metrics") and not correlated_hits:
        return None

    return _entrada_de_alerta(rule, detalle, correlated_hits)


def evaluate_alerts(
    db: Session,
    *,
    organization_id: Optional[str],
) -> dict[str, Any]:
    rules = list_alert_rules(db, organization_id=organization_id)
    log = _get_json(db, LOG_KEY, organization_id, default=[])
    triggered = []

    for rule in rules:
        entrada = _alerta_de_la_regla(db, organization_id, rule)
        if entrada is None:
            continue
        triggered.append(entrada)
        log.append(entrada)
        rule["last_triggered_at"] = entrada["triggered_at"]

    log = log[-_MAX_ENTRADAS_DE_REGISTRO:]
    _set_json(db, LOG_KEY, organization_id, log, description="BI Smart Alert log (JSON)")
    _set_json(db, RULES_KEY, organization_id, rules, description="BI Smart Alert rules (JSON)")

    return {
        "evaluated_at": _iso_now(),
        "rules_evaluated": len([r for r in rules if r.get("enabled", True)]),
        "triggered_count": len(triggered),
        "triggered": triggered,
    }


def default_alert_rules() -> list[dict[str, Any]]:
    """Seed defaults for a fresh org — can be called from setup flows."""
    return [
        {
            "id": "default-trend-revenue-down",
            "name": "Caída sostenida de ingresos",
            "metric_key": "revenue",
            "condition": "trend_down",
            "threshold": None,
            "trend_periods": 3,
            "severity": "critical",
            "cooldown_minutes": 1440,
            "enabled": True,
            "correlated_metrics": ["margin"],
            "notification_channels": ["ui"],
            "created_by": None,
            "created_at": _iso_now(),
            "last_triggered_at": None,
        },
        {
            "id": "default-anomaly-revenue",
            "name": "Anomalía de ingresos (z-score)",
            "metric_key": "revenue",
            "condition": "anomaly",
            "threshold": None,
            "trend_periods": 3,
            "severity": "warning",
            "cooldown_minutes": 720,
            "enabled": True,
            "correlated_metrics": [],
            "notification_channels": ["ui"],
            "created_by": None,
            "created_at": _iso_now(),
            "last_triggered_at": None,
        },
    ]


def seed_default_rules_if_empty(db: Session, *, organization_id: Optional[str]) -> None:
    rules = list_alert_rules(db, organization_id=organization_id)
    if not rules:
        _set_json(db, RULES_KEY, organization_id, default_alert_rules(),
                  description="BI Smart Alert rules (JSON)")
