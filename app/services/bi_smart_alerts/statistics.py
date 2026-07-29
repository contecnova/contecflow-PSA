"""Statistical helpers and cooldown logic for the BI Smart Alerts engine."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


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
    last_dt = datetime.fromisoformat(last)
    now = datetime.now(timezone.utc)
    if last_dt.tzinfo is None:
        last_dt = last_dt.replace(tzinfo=timezone.utc)
    return (now - last_dt).total_seconds() < cooldown * 60
