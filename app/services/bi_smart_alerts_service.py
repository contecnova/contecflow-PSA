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

def evaluate_alerts(
    db: Session,
    *,
    organization_id: Optional[str],
) -> dict[str, Any]:
    rules = list_alert_rules(db, organization_id=organization_id)
    log = _get_json(db, LOG_KEY, organization_id, default=[])
    triggered = []

    for rule in rules:
        if not rule.get("enabled", True):
            continue
        if _is_cooldown_active(rule):
            continue

        metric_key = rule.get("metric_key", "")
        condition = rule.get("condition", "")
        values = _fetch_metric_series(db, metric_key, organization_id)

        if not values:
            continue

        current = values[-1]
        threshold = rule.get("threshold")
        trend_periods = max(2, int(rule.get("trend_periods", 3)))
        fired = False
        detail: dict[str, Any] = {"current_value": current, "metric_key": metric_key}

        if condition == "threshold_above" and threshold is not None and current > threshold:
            fired = True
            detail["threshold"] = threshold

        elif condition == "threshold_below" and threshold is not None and current < threshold:
            fired = True
            detail["threshold"] = threshold

        elif condition == "trend_up":
            window = values[-trend_periods:]
            if len(window) >= 2:
                fired = all(window[i] < window[i + 1] for i in range(len(window) - 1))
                detail["trend_window"] = window

        elif condition == "trend_down":
            window = values[-trend_periods:]
            if len(window) >= 2:
                fired = all(window[i] > window[i + 1] for i in range(len(window) - 1))
                detail["trend_window"] = window

        elif condition == "anomaly":
            anomaly_eval = _historical_anomaly(values)
            fired = bool(anomaly_eval["is_anomaly"])
            detail.update(anomaly_eval)

        if not fired:
            continue

        # Check correlated metrics
        correlated_hits = []
        for corr_metric in (rule.get("correlated_metrics") or []):
            corr_values = _fetch_metric_series(db, corr_metric, organization_id)
            if not corr_values:
                continue
            size = min(len(values), len(corr_values), 12)
            corr_coeff = _pearson_corr(values[-size:], corr_values[-size:])
            corr_anomaly = _historical_anomaly(corr_values)
            current_diff = current - values[-2] if len(values) >= 2 else 0.0
            corr_diff = corr_values[-1] - corr_values[-2] if len(corr_values) >= 2 else 0.0
            aligned = (current_diff >= 0 and corr_diff >= 0) or (current_diff <= 0 and corr_diff <= 0)
            is_correlated_alert = abs(corr_coeff) >= 0.55 and bool(corr_anomaly["is_anomaly"]) and aligned
            if is_correlated_alert:
                correlated_hits.append({
                    "metric_key": corr_metric,
                    "current_value": round(float(corr_values[-1]), 3),
                    "corr_coef": round(float(corr_coeff), 3),
                    "z_score": corr_anomaly["z_score"],
                    "robust_z": corr_anomaly["robust_z"],
                })

        if rule.get("correlated_metrics") and not correlated_hits:
            continue

        entry: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "rule_id": rule["id"],
            "rule_name": rule.get("name", ""),
            "metric_key": metric_key,
            "condition": condition,
            "severity": rule.get("severity", "warning"),
            "detail": detail,
            "correlated": correlated_hits,
            "triggered_at": _iso_now(),
            "acknowledged": False,
            "acknowledged_by": None,
            "acknowledged_at": None,
        }
        triggered.append(entry)
        log.append(entry)
        rule["last_triggered_at"] = entry["triggered_at"]

    # Cap log at 500 entries
    log = log[-500:]
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
