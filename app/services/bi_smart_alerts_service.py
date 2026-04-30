"""BI Smart Alerts service.

Intelligent alert rules that go beyond simple thresholds:
- Trend-based alerts (sustained rise/drop over N periods)
- Anomaly-escalation alerts (z-score based)
- Cross-metric correlation alerts (if A triggers → check B)
- Alert fatigue reduction (cooldown windows)
- Alert history + acknowledgment

State is persisted in AppSetting JSON, scoped by organization.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.settings import AppSetting
from app.models.user import User

RULES_KEY = "bi.smart_alerts.rules"
LOG_KEY = "bi.smart_alerts.log"

SUPPORTED_METRICS = {
    "revenue": "Ingresos mensuales",
    "margin": "Margen bruto",
    "utilization": "Utilización del equipo",
    "tickets_open": "Tickets abiertos",
    "tasks_overdue": "Tareas vencidas",
    "budget_used_pct": "% Presupuesto consumido",
}

SUPPORTED_CONDITIONS = ["threshold_above", "threshold_below", "trend_up", "trend_down", "anomaly"]


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _setting_row(db: Session, key: str, organization_id: Optional[str]) -> Optional[AppSetting]:
    q = db.query(AppSetting).filter(AppSetting.key == key)
    if organization_id:
        q = q.filter(AppSetting.organization_id == organization_id)
    else:
        q = q.filter(AppSetting.organization_id.is_(None))
    return q.first()


def _get_json(db: Session, key: str, organization_id: Optional[str], default: Any) -> Any:
    row = _setting_row(db, key, organization_id)
    if not row or not row.value:
        return default
    try:
        return json.loads(row.value)
    except Exception:
        return default


def _set_json(db: Session, key: str, organization_id: Optional[str], value: Any, description: str) -> None:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    row = _setting_row(db, key, organization_id)
    if not row:
        row = AppSetting(key=key, organization_id=organization_id, description=description, value=payload)
        db.add(row)
    else:
        row.value = payload
    db.commit()


# ── Rule CRUD ──────────────────────────────────────────────────────────────────

def list_alert_rules(db: Session, *, organization_id: Optional[str]) -> list[dict[str, Any]]:
    return _get_json(db, RULES_KEY, organization_id, default=[])


def create_alert_rule(
    db: Session,
    *,
    organization_id: Optional[str],
    payload: dict[str, Any],
    current_user: User,
) -> dict[str, Any]:
    rules = list_alert_rules(db, organization_id=organization_id)
    metric = str(payload.get("metric_key", "")).strip()
    condition = str(payload.get("condition", "")).strip()
    if metric not in SUPPORTED_METRICS:
        raise ValueError("unsupported_metric")
    if condition not in SUPPORTED_CONDITIONS:
        raise ValueError("unsupported_condition")

    threshold = payload.get("threshold")
    if condition in ("threshold_above", "threshold_below") and threshold is None:
        raise ValueError("threshold_required")

    row: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "name": str(payload.get("name", f"Alert {metric}")).strip() or f"Alert {metric}",
        "metric_key": metric,
        "condition": condition,
        "threshold": float(threshold) if threshold is not None else None,
        "trend_periods": int(payload.get("trend_periods", 3)),
        "severity": str(payload.get("severity", "warning")) if payload.get("severity") in ("info", "warning", "critical") else "warning",
        "cooldown_minutes": max(5, int(payload.get("cooldown_minutes", 60))),
        "enabled": bool(payload.get("enabled", True)),
        "correlated_metrics": list(payload.get("correlated_metrics") or []),
        "notification_channels": list(payload.get("notification_channels") or ["ui"]),
        "created_by": current_user.id,
        "created_at": _iso_now(),
        "last_triggered_at": None,
    }
    rules.append(row)
    _set_json(db, RULES_KEY, organization_id, rules, description="BI Smart Alert rules (JSON)")
    return row


def update_alert_rule(
    db: Session,
    *,
    organization_id: Optional[str],
    rule_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    rules = list_alert_rules(db, organization_id=organization_id)
    target = next((r for r in rules if r.get("id") == rule_id), None)
    if not target:
        raise ValueError("rule_not_found")
    for field in ("name", "threshold", "trend_periods", "severity", "cooldown_minutes", "enabled",
                  "correlated_metrics", "notification_channels"):
        if field in payload and payload[field] is not None:
            target[field] = payload[field]
    _set_json(db, RULES_KEY, organization_id, rules, description="BI Smart Alert rules (JSON)")
    return target


def delete_alert_rule(db: Session, *, organization_id: Optional[str], rule_id: str) -> bool:
    rules = list_alert_rules(db, organization_id=organization_id)
    new_rules = [r for r in rules if r.get("id") != rule_id]
    if len(new_rules) == len(rules):
        return False
    _set_json(db, RULES_KEY, organization_id, new_rules, description="BI Smart Alert rules (JSON)")
    return True


# ── Alert log ─────────────────────────────────────────────────────────────────

def get_alert_log(db: Session, *, organization_id: Optional[str], limit: int = 100) -> list[dict[str, Any]]:
    log = _get_json(db, LOG_KEY, organization_id, default=[])
    return log[-limit:]


def acknowledge_alert(db: Session, *, organization_id: Optional[str], alert_id: str, current_user: User) -> dict[str, Any]:
    log = _get_json(db, LOG_KEY, organization_id, default=[])
    entry = next((e for e in log if e.get("id") == alert_id), None)
    if not entry:
        raise ValueError("alert_not_found")
    entry["acknowledged"] = True
    entry["acknowledged_by"] = current_user.id
    entry["acknowledged_at"] = _iso_now()
    _set_json(db, LOG_KEY, organization_id, log, description="BI Smart Alert log (JSON)")
    return entry


# ── Alert evaluation engine ────────────────────────────────────────────────────

def _z_score(values: list[float], v: float) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    var = sum((x - mean) ** 2 for x in values) / len(values)
    if var == 0:
        return 0.0
    import math
    return (v - mean) / math.sqrt(var)


def _pearson_corr(xs: list[float], ys: list[float]) -> float:
    if len(xs) != len(ys) or len(xs) < 3:
        return 0.0
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den_x = sum((x - mean_x) ** 2 for x in xs)
    den_y = sum((y - mean_y) ** 2 for y in ys)
    den = (den_x * den_y) ** 0.5
    if den == 0:
        return 0.0
    return num / den


def _historical_anomaly(values: list[float]) -> dict[str, Any]:
    if len(values) < 5:
        return {
            "is_anomaly": False,
            "z_score": 0.0,
            "robust_z": 0.0,
            "delta_pct": 0.0,
            "baseline_mean": 0.0,
            "baseline_std": 0.0,
        }

    current = float(values[-1])
    baseline = [float(v) for v in values[:-1]]
    z = _z_score(baseline, current)

    median = sorted(baseline)[len(baseline) // 2]
    mad = sorted(abs(v - median) for v in baseline)[len(baseline) // 2] or 1.0
    robust_z = 0.6745 * (current - median) / mad

    mean = sum(baseline) / len(baseline)
    var = sum((v - mean) ** 2 for v in baseline) / len(baseline)
    std = var ** 0.5
    denom = abs(mean) if abs(mean) > 1e-9 else 1.0
    delta_pct = ((current - mean) / denom) * 100.0

    is_anomaly = abs(z) >= 2.0 or abs(robust_z) >= 3.5 or abs(delta_pct) >= 35.0
    return {
        "is_anomaly": bool(is_anomaly),
        "z_score": round(z, 3),
        "robust_z": round(robust_z, 3),
        "delta_pct": round(delta_pct, 2),
        "baseline_mean": round(mean, 3),
        "baseline_std": round(std, 3),
    }


def _is_cooldown_active(rule: dict[str, Any]) -> bool:
    last = rule.get("last_triggered_at")
    if not last:
        return False
    cooldown = int(rule.get("cooldown_minutes", 60))
    from datetime import timedelta
    last_dt = datetime.fromisoformat(last)
    now = datetime.now(timezone.utc)
    if last_dt.tzinfo is None:
        last_dt = last_dt.replace(tzinfo=timezone.utc)
    return (now - last_dt).total_seconds() < cooldown * 60


def _fetch_metric_series(db: Session, metric_key: str, organization_id: Optional[str]) -> list[float]:
    """Pull last 12 months of the requested metric from real DB data."""
    from collections import defaultdict
    from datetime import date

    from app.services.bi_intelligence_service import _month_series
    try:
        series = _month_series(db, organization_id, months_history=24)
    except Exception:
        series = []

    if not series:
        series = [{"month": f"2025-{month:02d}", "revenue": 0.0, "cost": 0.0, "hours": 0.0} for month in range(1, 13)]

    def _empty_like() -> list[float]:
        return [0.0 for _ in series]

    if metric_key == "revenue":
        return [float(m.get("revenue", 0)) for m in series]
    if metric_key == "margin":
        return [float(m.get("revenue", 0)) - float(m.get("cost", 0)) for m in series]
    if metric_key == "utilization":
        out = []
        for m in series:
            hours = float(m.get("hours", 0) or 0)
            out.append(min(100.0, round((hours / 160.0) * 100.0, 2)))
        return out
    if metric_key == "budget_used_pct":
        out = []
        for m in series:
            revenue = float(m.get("revenue", 0) or 0)
            cost = float(m.get("cost", 0) or 0)
            out.append(round((cost / revenue) * 100.0, 2) if revenue > 0 else 0.0)
        return out
    if metric_key == "tickets_open":
        from app.models.service_desk import Ticket, TicketStatus

        start = date.fromisoformat(series[0]["month"] + "-01")
        rows = db.query(Ticket.created_at, Ticket.status).filter(Ticket.created_at >= start).all()
        buckets = defaultdict(float)
        for created_at, status in rows:
            if not created_at:
                continue
            month_key = f"{created_at.year:04d}-{created_at.month:02d}"
            if str(getattr(status, "value", status)) not in ("closed", "resolved", "cancelled"):
                buckets[month_key] += 1.0
        return [float(buckets.get(m["month"], 0.0)) for m in series]
    if metric_key == "tasks_overdue":
        from app.models.task import Task, TaskStatus

        start = date.fromisoformat(series[0]["month"] + "-01")
        rows = db.query(Task.due_date, Task.status).filter(Task.due_date != None, Task.due_date >= start).all()  # noqa: E711
        buckets = defaultdict(float)
        for due_date, status in rows:
            if not due_date:
                continue
            month_key = f"{due_date.year:04d}-{due_date.month:02d}"
            if str(getattr(status, "value", status)) not in ("done", "cancelled"):
                buckets[month_key] += 1.0
        return [float(buckets.get(m["month"], 0.0)) for m in series]
    if metric_key == "active_projects":
        return [1.0 if float(m.get("hours", 0) or 0) > 0 else 0.0 for m in series]
    return _empty_like()


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
